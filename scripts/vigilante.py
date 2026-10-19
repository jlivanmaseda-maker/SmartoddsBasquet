"""Vigilante de SmartOdds Basquet (19-oct-2026). Metodo del TT v2: avisa por
Telegram al CAMBIAR (algo falla / vuelve) y recuerda cada RECORDAR_H lo que siga
mal. Nunca toca la BD: solo lee.

Cada 10 min (cron, sin argumentos):
  servicio    /status responde, el scheduler corre, la version es la de VERSION
  ciclo       la ultima pasada de cuotas ("Fetch completo" en app.log) tiene
              menos de CICLO_MAX_MIN; la de resultados no se ve en el log, se
              vigila por sus efectos (resultados, picks)
  cuotas      si hay partidos en las proximas 48 h, alguna cuota se actualizo
              hace menos de CUOTAS_MAX_MIN
  resultados  partidos sin resolver mas de RES_MAX_H despues del inicio
              (la guarda de aplazados es de 72 h: se avisa a las 78 h, o si
              hay >= RES_MAX_N pendientes)
  picks       ningun pick activo de un partido ya resuelto; ninguno activo de
              un partido que empezo hace mas de PICK_MAX_H
  clv         de los picks liquidados en 7 dias, < CLV_SIN_MAX sin CLV
  cordura     picks de 24 h: probabilidad en rango, edge coherente con la
              cuota, mediana <= mejor cuota, version informada
  creditos    cupo de The Odds API (linea "creditos: restantes=" del log) por
              encima de CREDITOS_MIN y vista en las ultimas 2 h
  errores     lineas [ERROR] en app.log en los ultimos ERRORES_MIN minutos
  bd          la BD y su WAL existen y el WAL no crece sin control

Diario (--resumen): ademas canario (entradas fijas -> salida identica a
scripts/canario_esperado.json), PRAGMA quick_check y el resumen de la sombra
por regla (ROI a cuota cogida y a mediana +- 2 errores, CLV), que se envia
siempre.

  python scripts/vigilante.py [--resumen] [--canario-generar] [--sin-telegram]
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

LOGS = Path(os.getenv("BASKET_LOGS", ROOT / "logs"))
ESTADO = Path(os.getenv("BASKET_VIGILANTE_ESTADO", LOGS / "vigilante_estado.json"))
ESPERADO = ROOT / "scripts" / "canario_esperado.json"
STATUS_URL = os.getenv("BASKET_STATUS_URL", "http://127.0.0.1:8002/status")

RECORDAR_H = 6
CICLO_MAX_MIN = 35          # cuotas cada 15 min: dos ciclos perdidos
CUOTAS_MAX_MIN = 35
RES_MAX_H = 78              # guarda de aplazados 72 h + margen
RES_MAX_N = 5
PICK_MAX_H = 8
CLV_SIN_MAX = 0.30
CREDITOS_MIN = int(os.getenv("BASKET_CREDITOS_MIN", "100000"))
CREDITOS_VISTO_MAX_H = 2
ERRORES_MIN = 15
WAL_MAX_MB = 512
RE_FECHA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _hace(s: float) -> str:
    m = int(s // 60)
    return f"{m} min" if m < 120 else f"{m // 60} h"


def _naive(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace("T", " ")[:26])
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


# ──────────────────────────────────────────────────────────────
# Log
# ──────────────────────────────────────────────────────────────

def _tail_log(max_bytes: int = 3_000_000) -> list[str]:
    """Ultimas lineas de app.log (y app.log.1 si app.log es corto)."""
    out: list[str] = []
    for name in ("app.log.1", "app.log"):
        p = LOGS / name
        if not p.exists():
            continue
        try:
            with open(p, "rb") as f:
                f.seek(max(0, p.stat().st_size - max_bytes))
                out.extend(f.read().decode("utf-8", "replace").splitlines())
        except OSError:
            pass
    return out


def _ultima_linea(lineas: list[str], patron: str):
    """(fecha, linea) de la ultima linea del log que contiene `patron`."""
    for ln in reversed(lineas):
        if patron in ln:
            m = RE_FECHA.match(ln)
            if m:
                return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), ln
    return None, None


# ──────────────────────────────────────────────────────────────
# Checks
# ──────────────────────────────────────────────────────────────

def check_servicio(ahora: datetime) -> tuple:
    import httpx
    try:
        r = httpx.get(STATUS_URL, timeout=10)
        d = r.json()
    except Exception as e:  # noqa: BLE001
        return False, f"servicio: /status no responde ({type(e).__name__})"
    if d.get("status") != "ok":
        return False, f"servicio: /status dice {d.get('status')!r}"
    sch = d.get("scheduler") or {}
    if not sch.get("running"):
        return False, "servicio: el scheduler no corre"
    for j in sch.get("jobs", []):
        nr = j.get("next_run")
        if nr:
            t = _naive(datetime.fromisoformat(nr))
            if t < ahora - timedelta(minutes=5):
                return False, f"servicio: el job {j.get('id')} tenia que correr hace {_hace((ahora - t).total_seconds())}"
    try:
        esperada = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        esperada = ""
    if esperada and d.get("version") != esperada:
        return False, f"servicio: corre la version {d.get('version')!r} y VERSION dice {esperada!r} (¿sin reiniciar?)"
    return True, f"servicio: ok ({d.get('version')}, regla {d.get('rule_version')})"


def check_ciclo(lineas: list[str], ahora: datetime) -> tuple:
    t, _ = _ultima_linea(lineas, "Fetch completo")
    if t is None:
        return False, "ciclo: ninguna pasada de cuotas en el log"
    edad = (ahora - t).total_seconds()
    if edad > CICLO_MAX_MIN * 60:
        return False, f"ciclo: la ultima pasada de cuotas fue hace {_hace(edad)}"
    return True, f"ciclo: ok (hace {_hace(edad)})"


def check_cuotas(db, ahora: datetime) -> tuple:
    from app.models.match import Match
    from app.models.odds import Odds
    proximos = db.query(Match).filter(
        Match.is_completed == False,  # noqa: E712
        Match.commence_time > ahora, Match.commence_time < ahora + timedelta(hours=48),
    ).count()
    if not proximos:
        return True, "cuotas: ok (sin partidos en 48 h)"
    from sqlalchemy import func
    ultima = db.query(func.max(Odds.last_updated)).scalar()
    ultima = _naive(ultima)
    if ultima is None:
        return False, f"cuotas: {proximos} partidos proximos y ninguna cuota guardada"
    edad = (ahora - ultima).total_seconds()
    if edad > CUOTAS_MAX_MIN * 60:
        return False, f"cuotas: {proximos} partidos proximos y la ultima cuota es de hace {_hace(edad)}"
    return True, f"cuotas: ok ({proximos} partidos en 48 h, ultima hace {_hace(edad)})"


def check_resultados(db, ahora: datetime) -> tuple:
    from app.models.match import Match
    pend = db.query(Match).filter(
        Match.is_completed == False,  # noqa: E712
        Match.commence_time < ahora - timedelta(hours=PICK_MAX_H),
    ).all()
    viejos = [m for m in pend if _naive(m.commence_time) < ahora - timedelta(hours=RES_MAX_H)]
    if viejos:
        m = viejos[0]
        return False, (f"resultados: {len(viejos)} partido(s) sin resolver mas de {RES_MAX_H} h "
                       f"(p. ej. {m.home_team} vs {m.away_team}, {str(m.commence_time)[:16]})")
    if len(pend) >= RES_MAX_N:
        return False, f"resultados: {len(pend)} partidos sin resolver mas de {PICK_MAX_H} h despues del inicio"
    return True, f"resultados: ok ({len(pend)} pendientes recientes)"


def check_picks(db, ahora: datetime) -> tuple:
    from app.models.bet import Pick
    from app.models.match import Match
    q = db.query(Pick).join(Match, Match.id == Pick.match_id).filter(Pick.is_active == True)  # noqa: E712
    sin_liquidar = q.filter(Match.is_completed == True).count()  # noqa: E712
    colgados = q.filter(Match.commence_time < ahora - timedelta(hours=PICK_MAX_H)).count()
    fallos = []
    if sin_liquidar:
        fallos.append(f"{sin_liquidar} pick(s) activos de partidos ya resueltos")
    if colgados:
        fallos.append(f"{colgados} pick(s) activos de partidos que empezaron hace mas de {PICK_MAX_H} h")
    if fallos:
        return False, "picks: " + "; ".join(fallos)
    return True, "picks: ok"


def check_clv(db, ahora: datetime) -> tuple:
    from app.models.bet import Pick
    ps = db.query(Pick).filter(Pick.result.in_(["won", "lost"]),
                               Pick.resolved_at >= ahora - timedelta(days=7)).all()
    if len(ps) < 5:
        return True, f"clv: ok (solo {len(ps)} picks liquidados en 7 dias)"
    sin = sum(1 for p in ps if p.clv_pct is None)
    if sin / len(ps) > CLV_SIN_MAX:
        return False, f"clv: {sin} de {len(ps)} picks liquidados en 7 dias sin CLV"
    return True, f"clv: ok ({len(ps) - sin} de {len(ps)} con CLV)"


def check_cordura(db, ahora: datetime, settings) -> tuple:
    from app.models.bet import Pick
    ps = db.query(Pick).filter(Pick.created_at >= ahora - timedelta(hours=24)).all()
    if not ps:
        return True, "cordura: ok (sin picks en 24 h)"
    fallos = []
    for p in ps:
        prob, odds = p.estimated_probability, p.best_odds
        if prob is None or not (0.05 < prob < 0.97):
            fallos.append(f"#{p.id} probabilidad {prob}")
            continue
        if not odds or odds <= 1.0:
            fallos.append(f"#{p.id} cuota {odds}")
            continue
        edge = (prob - 1.0 / odds) / (1.0 / odds) * 100.0
        if p.edge is None or abs(edge - p.edge) > 0.1:
            fallos.append(f"#{p.id} edge guardado {p.edge} y recalculado {edge:.2f}")
        if not (settings.SYSTEM_MIN_EDGE - 0.01 <= (p.edge or 0) <= settings.SA_MAX_EDGE + 0.01):
            fallos.append(f"#{p.id} edge {p.edge} fuera de {settings.SYSTEM_MIN_EDGE}-{settings.SA_MAX_EDGE}")
        if p.median_soft_odds and p.median_soft_odds > odds + 1e-9:
            fallos.append(f"#{p.id} mediana {p.median_soft_odds} > mejor cuota {odds}")
        if not p.rule_version:
            fallos.append(f"#{p.id} sin version de regla")
    if fallos:
        return False, f"cordura: {len(fallos)} problema(s) en {len(ps)} picks de 24 h: " + "; ".join(fallos[:3])
    return True, f"cordura: ok ({len(ps)} picks en 24 h)"


def check_creditos(lineas: list[str], ahora: datetime) -> tuple:
    t, ln = _ultima_linea(lineas, "creditos: restantes=")
    if t is None:
        return True, "creditos: sin dato aun (la linea sale a INFO desde sharp-v2)"
    m = re.search(r"restantes=(\d+)", ln or "")
    restantes = int(m.group(1)) if m else None
    edad = (ahora - t).total_seconds()
    if edad > CREDITOS_VISTO_MAX_H * 3600:
        return False, f"creditos: el ultimo dato es de hace {_hace(edad)} (¿no se llama a la API?)"
    if restantes is not None and restantes < CREDITOS_MIN:
        return False, f"creditos: quedan {restantes:,} (< {CREDITOS_MIN:,})".replace(",", ".")
    return True, f"creditos: ok ({restantes:,} restantes)".replace(",", ".")


def check_errores(lineas: list[str], ahora: datetime) -> tuple:
    desde = ahora - timedelta(minutes=ERRORES_MIN)
    errs = []
    for ln in lineas:
        if "[ERROR]" not in ln:
            continue
        m = RE_FECHA.match(ln)
        if m and datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") >= desde:
            errs.append(ln)
    if errs:
        primero = errs[0].split("[ERROR]", 1)[1].strip()[:160]
        return False, f"errores: {len(errs)} en {ERRORES_MIN} min, p. ej. {primero}"
    return True, "errores: ok"


def check_bd(db_path: Path) -> tuple:
    if not db_path.exists():
        return False, f"bd: no existe {db_path}"
    mb = db_path.stat().st_size / 1e6
    wal = db_path.with_name(db_path.name + "-wal")
    wal_mb = wal.stat().st_size / 1e6 if wal.exists() else 0.0
    if wal_mb > WAL_MAX_MB:
        return False, f"bd: el WAL ocupa {wal_mb:.0f} MB (> {WAL_MAX_MB}): no se hace checkpoint"
    return True, f"bd: ok ({mb:.0f} MB, WAL {wal_mb:.0f} MB)"


# ──────────────────────────────────────────────────────────────
# Canario (entradas fijas -> salida identica)
# ──────────────────────────────────────────────────────────────

CANARIO_OBK = {
    "pinnacle": {"odds_home": 1.87, "odds_away": 2.05},
    "betonlineag": {"odds_home": 1.88, "odds_away": 2.02},
    "lowvig": {"odds_home": 1.89, "odds_away": 2.01},
    "onexbet": {"odds_home": 1.86, "odds_away": 2.06},
    "draftkings": {"odds_home": 1.95, "odds_away": 1.95},
    "fanduel": {"odds_home": 2.00, "odds_away": 1.87},
    "betmgm": {"odds_home": 1.91, "odds_away": 1.95},
    "bovada": {"odds_home": 1.93, "odds_away": 1.93},
    "fanatics": {"odds_home": 1.97, "odds_away": 1.89},
    "betfair_ex_eu": {"odds_home": 2.10, "odds_away": 1.98},
}


def canario_calcular() -> dict:
    """Salida de las piezas del calculo con entradas fijas (sin BD)."""
    from app.ml.model import predict_match
    from app.services.clv_calculator import _devig_prob, clv_pct
    from app.services.value_calculator import _evaluate_side

    class T:  # equipo sintetico (lo que lee el modelo)
        def __init__(self, elo):
            self.elo_overall = elo
            self.net_rating = None
            self.win_rate_last_10 = None

    home = _evaluate_side(CANARIO_OBK, "odds_home", "odds_away", 0.5)
    away = _evaluate_side(CANARIO_OBK, "odds_away", "odds_home", 0.5)
    return {
        "home": home,
        "away": away,
        "devig": _devig_prob(1.87, 2.05),
        "clv": clv_pct(2.00, 1.9231),
        "modelo": predict_match(T(1550.0), T(1480.0)),
    }


def _plano(d, prefijo=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_plano(v, f"{prefijo}{k}."))
    else:
        out[prefijo.rstrip(".")] = d
    return out


def check_canario() -> tuple:
    if not ESPERADO.exists():
        return False, f"canario: falta {ESPERADO.name} (generar con --canario-generar)"
    try:
        esperado = _plano(json.loads(ESPERADO.read_text(encoding="utf-8")))
        actual = _plano(canario_calcular())
    except Exception as e:  # noqa: BLE001
        return False, f"canario: el calculo falla ({type(e).__name__}: {e})"[:300]
    difs = []
    for k in sorted(set(esperado) | set(actual)):
        a, b = esperado.get(k), actual.get(k)
        if isinstance(a, float) and isinstance(b, float):
            if not math.isclose(a, b, rel_tol=0, abs_tol=1e-9):
                difs.append(f"{k}: {a} -> {b}")
        elif a != b:
            difs.append(f"{k}: {a!r} -> {b!r}")
    if difs:
        return False, f"canario: {len(difs)} diferencia(s): " + "; ".join(difs[:4])
    return True, f"canario: ok ({len(actual)} valores identicos)"


def check_quick_check(db_path: Path) -> tuple:
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            r = con.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        return False, f"bd:integridad: no se puede comprobar ({type(e).__name__})"
    return (r == "ok"), f"bd:integridad: {r}"


# ──────────────────────────────────────────────────────────────
# Resumen de la sombra por regla
# ──────────────────────────────────────────────────────────────

def _roi_se(vals):
    n = len(vals)
    if not n:
        return (0, None, None)
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / n
    return (n, m * 100, 2 * (var ** 0.5) / (n ** 0.5) * 100)


def _f(t):
    n, roi, e2 = t
    return "sin picks" if not n else f"{roi:+.1f}% +-{e2:.0f} (n={n})"


def resumen_sombra(db, ahora: datetime) -> list[str]:
    from app.models.bet import Pick
    lineas = []
    creados = db.query(Pick).filter(Pick.created_at >= ahora - timedelta(hours=24)).count()
    liq = db.query(Pick).filter(Pick.resolved_at >= ahora - timedelta(hours=24)).count()
    activos = db.query(Pick).filter(Pick.is_active == True).count()  # noqa: E712
    lineas.append(f"picks 24 h: {creados} creados, {liq} liquidados; {activos} activos")
    ps = db.query(Pick).filter(Pick.result.in_(["won", "lost"])).all()
    por_regla = {}
    for p in ps:
        por_regla.setdefault(p.rule_version or "?", []).append(p)
    for rv, lst in sorted(por_regla.items()):
        cog = [(p.best_odds - 1) if p.result == "won" else -1.0 for p in lst if p.best_odds]
        med = [(p.median_soft_odds - 1) if p.result == "won" else -1.0 for p in lst if p.median_soft_odds]
        clvs = [p.clv_pct for p in lst if p.clv_pct is not None]
        clv = (f"CLV {sum(clvs) / len(clvs):+.1f}% ({100 * sum(1 for c in clvs if c > 0) / len(clvs):.0f}% >0)"
               if clvs else "sin CLV")
        first = min((p.created_at for p in lst if p.created_at), default=None)
        lineas.append(f"{rv} (desde {first.strftime('%d-%b') if first else '?'}): "
                      f"cogida {_f(_roi_se(cog))}; mediana {_f(_roi_se(med))}; {clv}")
    return lineas


# ──────────────────────────────────────────────────────────────
# Decidir y avisar
# ──────────────────────────────────────────────────────────────

def decidir(previo: dict, checks: dict, ahora: datetime) -> tuple[list[str], dict]:
    """(lineas a avisar, estado nuevo): fallos nuevos, recordatorios y lo que vuelve."""
    lineas, nuevo = [], {}
    for clave, (ok, texto) in sorted(checks.items()):
        p = previo.get(clave)
        if ok:
            if p is not None and not p.get("ok", True):
                lineas.append(f"OK vuelve: {p.get('texto', clave)}")
            nuevo[clave] = {"ok": True}
            continue
        if p is None or p.get("ok", True):
            lineas.append(f"MAL {texto}")
            nuevo[clave] = {"ok": False, "texto": texto, "desde": ahora.isoformat(), "avisado": ahora.isoformat()}
            continue
        avisado = datetime.fromisoformat(p.get("avisado", p.get("desde", ahora.isoformat())))
        if ahora - avisado >= timedelta(hours=RECORDAR_H):
            lineas.append(f"SIGUE MAL (desde {p.get('desde', '?')[:16]}): {texto}")
            nuevo[clave] = {**p, "texto": texto, "avisado": ahora.isoformat()}
        else:
            nuevo[clave] = {**p, "texto": texto}
    return lineas, nuevo


def _leer_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_estado(estado: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ESTADO)


def _telegram(texto: str) -> bool:
    try:
        from app.services.notification_service import _send_telegram
        return bool(_send_telegram(texto))
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] error: {e}")
        return False


def _db_path(settings) -> Path:
    url = settings.DATABASE_URL
    if not url.startswith("sqlite"):
        return Path("/nonexistent")
    p = url.split("///", 1)[1]
    path = Path(p)
    if not path.is_absolute():
        path = (ROOT / "backend" / p).resolve()
    return path


def comprobar(db, ahora: datetime, resumen: bool, settings) -> dict:
    lineas = _tail_log()
    out = {}
    out["servicio"] = check_servicio(ahora)
    out["ciclo"] = check_ciclo(lineas, ahora)
    out["cuotas"] = check_cuotas(db, ahora)
    out["resultados"] = check_resultados(db, ahora)
    out["picks"] = check_picks(db, ahora)
    out["clv"] = check_clv(db, ahora)
    out["cordura"] = check_cordura(db, ahora, settings)
    out["creditos"] = check_creditos(lineas, ahora)
    out["errores"] = check_errores(lineas, ahora)
    out["bd"] = check_bd(_db_path(settings))
    if resumen:
        out["canario"] = check_canario()
        out["bd:integridad"] = check_quick_check(_db_path(settings))
    return out


def main(argv: list[str]) -> int:
    resumen = "--resumen" in argv
    sin_tg = "--sin-telegram" in argv
    if "--canario-generar" in argv:
        ESPERADO.write_text(json.dumps(canario_calcular(), indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"canario esperado escrito en {ESPERADO}")
        return 0
    from app.config import settings
    from app.db.database import SessionLocal
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    db = SessionLocal()
    try:
        checks = {}
        try:
            checks = comprobar(db, ahora, resumen, settings)
        except Exception as e:  # noqa: BLE001
            checks["vigilante"] = (False, f"vigilante: fallo al comprobar ({type(e).__name__}: {e})"[:300])
        for clave, (ok, texto) in sorted(checks.items()):
            print(f"{ahora:%Y-%m-%d %H:%M} {'ok ' if ok else 'MAL'} {texto}")
        lineas, nuevo = decidir(_leer_estado(), checks, ahora)
        _guardar_estado(nuevo)
        if lineas and not sin_tg:
            _telegram("Basquet vigilante\n" + "\n".join(lineas))
        if resumen:
            mal = [t for ok, t in checks.values() if not ok]
            cuerpo = [f"Basquet sombra, resumen {ahora:%d-%b %H:%M} UTC"]
            cuerpo.append(("TODO OK" if not mal else "MAL: " + "; ".join(mal)) + f" ({len(checks)} checks)")
            try:
                cuerpo.extend(resumen_sombra(db, ahora))
            except Exception as e:  # noqa: BLE001
                cuerpo.append(f"resumen de la sombra: error {type(e).__name__}")
            print("\n".join(cuerpo))
            if not sin_tg:
                _telegram("\n".join(cuerpo))
        return 0 if all(ok for ok, _ in checks.values()) else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
