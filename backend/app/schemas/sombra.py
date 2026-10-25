"""Apartado de la sombra para la web (25-oct-2026): resumen por regla y mercado, picks y estado del sistema.

Mismo diseno y metodo que el apartado Sombra del TT (nada de su codigo): cada regla en prueba se mide aparte, a la
cuota cogida y a la MEDIANA de las casas blandas, con su error, su CLV contra el cierre de Pinnacle y, en handicap y
total, los puntos de linea ganados frente al cierre. Umbral para publicar una regla: >= 300 picks liquidados y ROI a
mediana menos 2 errores > 0.

Lo consume la pagina /picks del frontend (shadowRules, shadowPicks, systemStatus en graphql_schema.py).
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import strawberry

from app.config import settings
from app.db.database import SessionLocal
from app.models.bet import Pick
from app.models.match import Match
from app.models.odds import Odds
from app.version import APP_VERSION, RULE_VERSION, RULE_VERSION_LINES

UMBRAL_PICKS = 300
ROOT = Path(__file__).resolve().parents[3]
ESTADO_VIGILANTE = Path(os.getenv("BASKET_VIGILANTE_ESTADO", str(ROOT / "logs" / "vigilante_estado.json")))
SHARP = set(settings.SHARP_BOOKMAKERS)
EXCHANGES = {"betfair_ex_eu", "betfair_ex_uk", "betfair_ex_au", "matchbook", "smarkets"}

# (regla, mercado, nombre, descripcion) en el orden en que se ensenan
REGLAS = (
    ("sharp-v2", "ganador", "Ganador · sharp-v2",
     "Probabilidad sin margen de Pinnacle, BetOnline, LowVig y 1xBet contra la mejor casa blanda: pick con valor de "
     "3 a 12 %, cuota 1,20-5,00, hasta 24 h antes y con Pinnacle cotizando. Guarda la mediana y Pinnacle de cada pick "
     "(desde el 19-oct)."),
    ("sharp-v3", "handicap", "Hándicap · sharp-v3",
     "La línea de Pinnacle convertida a la línea de cada casa blanda: pick cuando una se queda desfasada con valor de "
     "3 a 12 % (desde el 20-oct)."),
    ("sharp-v3", "total", "Total de puntos · sharp-v3",
     "Igual que el hándicap, con el total de puntos (desde el 20-oct)."),
    ("sharp-v1", "ganador", "Ganador · sharp-v1 (histórico)",
     "La regla original, del 21-jun al 19-oct, antes de medir a mediana. Solo como referencia."),
)
NOMBRE = {(r, m): n for r, m, n, _ in REGLAS}


# ──────────────────────────────────────────────────────────────
# Tipos
# ──────────────────────────────────────────────────────────────

@strawberry.type
class ReglaType:
    clave: str
    regla: str
    mercado: str
    nombre: str
    descripcion: str
    desde: Optional[datetime]
    picks: int
    abiertos: int
    liquidados: int
    ganados: int
    nulos: int
    unidades: float
    roi: Optional[float]
    roi_error: Optional[float]
    roi_mediana: Optional[float]
    roi_mediana_error: Optional[float]
    n_mediana: int
    clv: Optional[float]
    clv_positivos: Optional[float]
    n_clv: int
    linea_vs_cierre: Optional[float]
    n_linea: int
    cuota_media: Optional[float]
    objetivo: int
    cumple_umbral: bool


@strawberry.type
class CasaCuotaType:
    casa: str
    cuota: float


@strawberry.type
class PickSombraType:
    id: int
    clave: str
    regla_nombre: str
    mercado: str
    liga: Optional[str]
    inicio: Optional[datetime]
    creado: Optional[datetime]
    horas_antes: Optional[float]
    local: str
    visitante: str
    seleccion: str
    cuota: Optional[float]
    casa: Optional[str]
    cuota_mediana: Optional[float]
    n_casas: Optional[int]
    cuota_minima: Optional[float]
    pinnacle_justa: Optional[float]
    edge: Optional[float]
    estado: str
    beneficio: Optional[float]
    clv: Optional[float]
    cuota_cierre_justa: Optional[float]
    linea_vs_cierre: Optional[float]
    marcador: Optional[str]
    casas: List[CasaCuotaType]


@strawberry.type
class EstadoSistemaType:
    version: str
    regla_ganador: str
    regla_lineas: str
    lineas_activas: bool
    vigilante_ok: Optional[bool]
    vigilante_fallos: List[str]
    vigilante_actualizado: Optional[datetime]
    creditos_restantes: Optional[int]


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def mercado_de(bet_type: str) -> str:
    if bet_type.startswith("spread_"):
        return "handicap"
    if bet_type.startswith("total_points_"):
        return "total"
    return "ganador"


def _estado(p: Pick) -> str:
    return {"won": "ganado", "lost": "perdido", "void": "nulo"}.get(p.result or "", "abierto")


def _roi(vals: list) -> tuple:
    """(ROI %, 2 errores estandar %) de una lista de resultados por unidad apostada."""
    n = len(vals)
    if not n:
        return None, None
    m = sum(vals) / n
    if n < 2:
        return round(100 * m, 1), None
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    return round(100 * m, 1), round(200 * math.sqrt(var / n), 1)


def _num(x: float) -> str:
    return f"{x:+.1f}" if x else "0"


def seleccion(bet_type: str, local: str, visitante: str) -> str:
    """Texto legible de la apuesta."""
    if bet_type == "match_winner_home":
        return f"Gana {local}"
    if bet_type == "match_winner_away":
        return f"Gana {visitante}"
    try:
        if bet_type.startswith("spread_home_"):
            return f"{local} {_num(float(bet_type[len('spread_home_'):]))}"
        if bet_type.startswith("spread_away_"):
            return f"{visitante} {_num(float(bet_type[len('spread_away_'):]))}"
        if bet_type.startswith("total_points_over_"):
            return f"Más de {float(bet_type[len('total_points_over_'):]):.1f} puntos"
        if bet_type.startswith("total_points_under_"):
            return f"Menos de {float(bet_type[len('total_points_under_'):]):.1f} puntos"
    except ValueError:
        pass
    return bet_type


def cuota_minima(p: Pick) -> Optional[float]:
    """Cuota a la que el pick todavia da el valor minimo de la regla (SYSTEM_MIN_EDGE).

    Ganador: (1 + edge_min) / p. Handicap y total: el push devuelve la unidad, asi que
    (1 + edge_min - p_push) / p_gana, con p_push deducido de la cuota justa de Pinnacle guardada
    ((1 - p_push) / p_gana)."""
    prob = p.estimated_probability
    if not prob or prob <= 0:
        return None
    e = settings.SYSTEM_MIN_EDGE / 100.0
    if mercado_de(p.bet_type) == "ganador":
        return round((1 + e) / prob, 2)
    p_push = 0.0
    if p.pinnacle_fair_at_pick:
        p_push = min(max(1.0 - p.pinnacle_fair_at_pick * prob, 0.0), 0.2)
    return round((1 + e - p_push) / prob, 2)


def _casas_ahora(p: Pick, odds_rows: list) -> List[CasaCuotaType]:
    """Precio de cada casa blanda AHORA para la misma apuesta (misma linea), de mayor a menor."""
    out = []
    bt = p.bet_type
    for o in odds_rows:
        if o.bookmaker in SHARP or o.bookmaker in EXCHANGES:
            continue
        cuota = None
        if bt == "match_winner_home":
            cuota = o.odds_home
        elif bt == "match_winner_away":
            cuota = o.odds_away
        elif p.line_value is not None and bt.startswith("spread_"):
            home = bt.startswith("spread_home_")
            linea_local = p.line_value if home else -p.line_value
            if o.spread_line is not None and abs(o.spread_line - linea_local) < 1e-9:
                cuota = o.odds_spread_home if home else o.odds_spread_away
        elif p.line_value is not None and bt.startswith("total_points_"):
            if o.total_line is not None and abs(o.total_line - p.line_value) < 1e-9:
                cuota = o.odds_over if "_over_" in bt else o.odds_under
        if cuota and cuota > 1.0:
            out.append(CasaCuotaType(casa=o.bookmaker, cuota=round(cuota, 2)))
    out.sort(key=lambda c: -c.cuota)
    return out[:10]


def _desde(dias: Optional[int]) -> Optional[datetime]:
    return datetime.utcnow() - timedelta(days=dias) if dias else None


# ──────────────────────────────────────────────────────────────
# Consultas
# ──────────────────────────────────────────────────────────────

def reglas(dias: Optional[int] = None) -> List[ReglaType]:
    db = SessionLocal()
    try:
        versiones = sorted({r for r, _, _, _ in REGLAS})
        todos = db.query(Pick).filter(Pick.rule_version.in_(versiones)).all()
        primero = {}
        for p in todos:
            k = (p.rule_version, mercado_de(p.bet_type))
            if p.created_at and (k not in primero or p.created_at < primero[k]):
                primero[k] = p.created_at
        corte = _desde(dias)
        grupos: dict = {}
        for p in todos:
            if corte and (not p.created_at or p.created_at < corte):
                continue
            grupos.setdefault((p.rule_version, mercado_de(p.bet_type)), []).append(p)
        out = []
        for regla, mercado, nombre, descripcion in REGLAS:
            ps = grupos.get((regla, mercado), [])
            if not ps:
                continue
            liq = [p for p in ps if p.result in ("won", "lost")]
            cog = [((p.best_odds - 1) if p.result == "won" else -1.0) for p in liq if p.best_odds]
            med = [((p.median_soft_odds - 1) if p.result == "won" else -1.0) for p in liq if p.median_soft_odds]
            clvs = [p.clv_pct for p in liq if p.clv_pct is not None]
            lineas = [p.line_clv for p in liq if p.line_clv is not None]
            cuotas = [p.best_odds for p in ps if p.best_odds]
            roi, roi_e = _roi(cog)
            roi_m, roi_m_e = _roi(med)
            out.append(ReglaType(
                clave=f"{regla}|{mercado}", regla=regla, mercado=mercado, nombre=nombre, descripcion=descripcion,
                desde=primero.get((regla, mercado)),
                picks=len(ps),
                abiertos=sum(1 for p in ps if p.result is None),
                liquidados=len(liq),
                ganados=sum(1 for p in liq if p.result == "won"),
                nulos=sum(1 for p in ps if p.result == "void"),
                unidades=round(sum(p.profit_units or 0.0 for p in ps if p.result), 2),
                roi=roi, roi_error=roi_e, roi_mediana=roi_m, roi_mediana_error=roi_m_e, n_mediana=len(med),
                clv=round(sum(clvs) / len(clvs), 1) if clvs else None,
                clv_positivos=round(100 * sum(1 for c in clvs if c > 0) / len(clvs), 0) if clvs else None,
                n_clv=len(clvs),
                linea_vs_cierre=round(sum(lineas) / len(lineas), 2) if lineas else None,
                n_linea=len(lineas),
                cuota_media=round(sum(cuotas) / len(cuotas), 2) if cuotas else None,
                objetivo=UMBRAL_PICKS,
                cumple_umbral=bool(len(liq) >= UMBRAL_PICKS and roi_m is not None and roi_m_e is not None
                                   and roi_m - roi_m_e > 0),
            ))
        return out
    finally:
        db.close()


def picks(dias: Optional[int] = None, clave: Optional[str] = None, estado: Optional[str] = None,
          liga: Optional[str] = None, limit: int = 300) -> List[PickSombraType]:
    db = SessionLocal()
    try:
        versiones = sorted({r for r, _, _, _ in REGLAS})
        q = db.query(Pick).filter(Pick.rule_version.in_(versiones))
        corte = _desde(dias)
        if corte:
            q = q.filter(Pick.created_at >= corte)
        if estado == "abiertos":
            q = q.filter(Pick.result.is_(None))
        elif estado == "liquidados":
            q = q.filter(Pick.result.isnot(None))
        regla_f = mercado_f = None
        if clave and "|" in clave:
            regla_f, mercado_f = clave.split("|", 1)
            q = q.filter(Pick.rule_version == regla_f)
        lista = q.all()
        if mercado_f:
            lista = [p for p in lista if mercado_de(p.bet_type) == mercado_f]
        matches = {m.id: m for m in db.query(Match).filter(Match.id.in_({p.match_id for p in lista})).all()} \
            if lista else {}
        if liga:
            lista = [p for p in lista if (matches.get(p.match_id) and matches[p.match_id].league_tier == liga)]
        if estado == "abiertos":
            lista.sort(key=lambda p: (matches[p.match_id].commence_time if p.match_id in matches else datetime.max))
        else:
            lista.sort(key=lambda p: (p.resolved_at or p.created_at or datetime.min), reverse=True)
        lista = lista[:limit]
        odds_por_partido: dict = {}
        abiertos = {p.match_id for p in lista if p.result is None}
        if abiertos:
            for o in db.query(Odds).filter(Odds.match_id.in_(abiertos)).all():
                odds_por_partido.setdefault(o.match_id, []).append(o)
        out = []
        for p in lista:
            m = matches.get(p.match_id)
            if not m:
                continue
            mercado = mercado_de(p.bet_type)
            horas = None
            if m.commence_time and p.created_at:
                horas = round((m.commence_time.replace(tzinfo=None) - p.created_at.replace(tzinfo=None))
                              .total_seconds() / 3600, 1)
            out.append(PickSombraType(
                id=p.id, clave=f"{p.rule_version}|{mercado}",
                regla_nombre=NOMBRE.get((p.rule_version, mercado), p.rule_version or "?"),
                mercado=mercado, liga=m.league_tier, inicio=m.commence_time, creado=p.created_at,
                horas_antes=horas, local=m.home_team, visitante=m.away_team,
                seleccion=seleccion(p.bet_type, m.home_team, m.away_team),
                cuota=p.best_odds, casa=p.best_bookmaker, cuota_mediana=p.median_soft_odds,
                n_casas=p.n_soft_books, cuota_minima=cuota_minima(p),
                pinnacle_justa=p.pinnacle_fair_at_pick,
                edge=round(p.edge, 1) if p.edge is not None else None,
                estado=_estado(p), beneficio=p.profit_units, clv=p.clv_pct,
                cuota_cierre_justa=p.closing_odds, linea_vs_cierre=p.line_clv, marcador=m.score,
                casas=_casas_ahora(p, odds_por_partido.get(p.match_id, [])) if p.result is None else [],
            ))
        return out
    finally:
        db.close()


def estado_sistema() -> EstadoSistemaType:
    ok, fallos, actualizado = None, [], None
    try:
        estado = json.loads(ESTADO_VIGILANTE.read_text(encoding="utf-8"))
        fallos = [v.get("texto", k) for k, v in sorted(estado.items()) if not v.get("ok", True)]
        ok = not fallos
        actualizado = datetime.fromtimestamp(ESTADO_VIGILANTE.stat().st_mtime, tz=timezone.utc)
    except (OSError, ValueError):
        pass
    creditos = None
    try:
        from app.services.odds_fetcher import LAST_CREDITS
        if LAST_CREDITS.get("remaining") is not None:
            creditos = int(float(LAST_CREDITS["remaining"]))
    except Exception:  # noqa: BLE001
        pass
    return EstadoSistemaType(
        version=APP_VERSION, regla_ganador=RULE_VERSION, regla_lineas=RULE_VERSION_LINES,
        lineas_activas=bool(settings.LINE_MARKETS_ENABLED), vigilante_ok=ok, vigilante_fallos=fallos,
        vigilante_actualizado=actualizado, creditos_restantes=creditos,
    )
