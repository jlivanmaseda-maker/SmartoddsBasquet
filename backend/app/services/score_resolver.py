"""Score Resolver para Basket.

Resuelve partidos completados y liquida sus picks. Portado de tenis,
simplificado (basket no tiene retiradas ni sets):

  1. Encuentra matches pasados de commence_time aun sin completar.
  2. Obtiene el resultado final (Basketball Scores API / BetsAPI).
  3. Actualiza el Match (points_home/away, score, total_points, overtime).
  4. Liquida todos los Picks del match (won/lost/void).
  5. Devuelve el numero de partidos resueltos.

Diferencias clave vs tenis:
  - El resultado es solo dos enteros (points_home, points_away). No hay
    sets/games. score = "112-104"; total_points = points_home + points_away.
  - No existe la retirada. El unico caso de void es un partido
    APLAZADO/CANCELADO -> match.is_postponed = True y sus picks -> "void".
  - La prorroga (overtime) cuenta como parte del resultado final normal;
    NO afecta a la liquidacion del moneyline (el de mas puntos gana).
  - No hay empate: la prorroga garantiza un ganador.

Mercados liquidados (bet_type):
  - match_winner_home / match_winner_away  (moneyline 2 vias)
  - spread_home_X / spread_away_X          (handicap de puntos; push -> void)
  - total_points_over_X / total_points_under_X  (totals; push -> void)
"""
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.config import settings
from app.models.match import Match
from app.models.bet import Pick, UserBet
from app.services.odds_fetcher import describir_401

logger = logging.getLogger("smartodds_basketball.scores")

# Ultimo fallo de /scores por liga (31-oct-2026, cupo agotado). Mientras falla la consulta no se sabe nada de los
# partidos, y /scores solo devuelve los ultimos 3 dias: un partido que empezo antes de un fallo puede haber salido ya
# de esa ventana, asi que no se anula solo aunque la consulta vuelva a funcionar (se queda pendiente y el vigilante
# avisa a las 78 h; a mano: void_postponed_match(force=True)). Esta en memoria: un reinicio la borra.
_ULTIMO_FALLO_SCORES: dict = {}

# BetsAPI sport_id para basket. (Tennis=13, Table Tennis=92, Basketball=18.)
BETSAPI_BASKETBALL_SPORT_ID = 18
BETSAPI_BASE = "https://api.b365api.com/v1"

# Guarda para partidos sin resultado: los aplazados suelen rejugarse 1-2 dias
# despues, asi que no los voidamos inmediatamente.
POSTPONED_GUARD_HOURS = 72

# Solo consideramos "stale" partidos cuyo commence_time ya quedo atras un margen
# (un partido de basket dura ~2-2.5h con prorroga incluida).
STALE_AFTER_HOURS = 3


# ──────────────────────────────────────────────────────────────
# Parsing del score
# ──────────────────────────────────────────────────────────────

def parse_basketball_score(score_str: str) -> Optional[dict]:
    """Parsea un score de basket. Ej: '112-104'.

    Returns:
        {
            'points_home': 112,
            'points_away': 104,
            'total_points': 216,
        }
        o None si no es parseable / no hay marcador.
    """
    if not score_str:
        return None

    score_str = score_str.strip()
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", score_str)
    if not m:
        return None

    ph = int(m.group(1))
    pa = int(m.group(2))
    return {
        "points_home": ph,
        "points_away": pa,
        "total_points": ph + pa,
    }


# ──────────────────────────────────────────────────────────────
# Liquidacion de picks
# ──────────────────────────────────────────────────────────────

def resolve_match_picks(db: Session, match: Match) -> int:
    """Liquida todos los picks pendientes de un partido completado.

    Returns: numero de picks resueltos.
    """
    if not match.is_completed:
        return 0

    picks = db.query(Pick).filter(
        Pick.match_id == match.id,
        Pick.result.is_(None),
        Pick.is_active == True,
    ).all()

    if not picks:
        return 0

    now = datetime.now(timezone.utc)
    resolved = 0

    for pick in picks:
        result, profit = _resolve_single_pick(pick, match)
        if result:
            pick.result = result
            pick.profit_units = profit
            pick.resolved_at = now
            pick.is_active = False
            resolved += 1

    # CLV: cuota sharp al cierre (odds_history pre-tipoff) vs cuota cogida.
    # Nunca debe romper la liquidacion.
    try:
        from app.services.clv_calculator import compute_match_clv
        n_clv = compute_match_clv(db, match)
        if n_clv:
            logger.info(f"CLV calculado para {n_clv} picks de match #{match.id}")
    except Exception as e:
        logger.warning(f"CLV match #{match.id}: {e}")

    # Liquidar user_bets enlazadas a estos picks.
    try:
        ub = resolve_user_bets(db, match)
        if ub > 0:
            logger.info(
                f"Resueltas {ub} user_bets para {match.home_team} vs {match.away_team}"
            )
    except Exception:
        pass

    if resolved > 0:
        db.commit()
        logger.info(
            f"Resueltos {resolved} picks para {match.home_team} vs {match.away_team} "
            f"({match.score})"
        )

    return resolved


def _won(pick: Pick) -> tuple:
    """(result, profit) para un pick ganado."""
    odds = pick.best_odds or 1.0
    return ("won", round(odds - 1.0, 4))


def _lost() -> tuple:
    return ("lost", -1.0)


def _void() -> tuple:
    return ("void", 0.0)


def _parse_line(bet_type: str, prefix: str) -> Optional[float]:
    """Extrae la linea numerica del sufijo de un bet_type.

    Ej: ('spread_home_-5.5', 'spread_home_') -> -5.5
        ('total_points_over_215.5', 'total_points_over_') -> 215.5
    Soporta signo y decimales. Devuelve None si no es parseable.
    """
    suffix = bet_type[len(prefix):]
    try:
        return float(suffix)
    except (ValueError, TypeError):
        return None


def _resolve_single_pick(pick: Pick, match: Match) -> tuple:
    """Liquida un pick individual.

    Returns: (result, profit_units) o (None, None) si no se puede resolver.

    Politica:
      - Partido aplazado/cancelado (is_postponed) -> void siempre.
      - match_winner_*: gana quien tiene mas puntos (la prorroga ya garantiza
        un ganador; no afecta a la liquidacion).
      - spread_*: aplica la linea a los puntos del lado correspondiente y
        compara. Empate exacto (push) -> void.
      - total_points_over/under_X: compara total_points con X. Push -> void.
    """
    bt = pick.bet_type

    # Aplazado/cancelado -> void de todo.
    if match.is_postponed:
        return _void()

    ph = match.points_home
    pa = match.points_away
    if ph is None or pa is None:
        return (None, None)

    # ── Moneyline ──
    if bt == "match_winner_home":
        return _won(pick) if ph > pa else _lost()

    if bt == "match_winner_away":
        return _won(pick) if pa > ph else _lost()

    # ── Spread (handicap de puntos) ──
    # El equipo cubre si, sumando su linea a sus puntos, supera al rival.
    # Empate exacto tras aplicar la linea (linea entera) -> push -> void.
    if bt.startswith("spread_home_"):
        line = _parse_line(bt, "spread_home_")
        if line is None:
            return (None, None)
        margin = (ph + line) - pa
        if margin > 0:
            return _won(pick)
        if margin < 0:
            return _lost()
        return _void()  # push

    if bt.startswith("spread_away_"):
        line = _parse_line(bt, "spread_away_")
        if line is None:
            return (None, None)
        margin = (pa + line) - ph
        if margin > 0:
            return _won(pick)
        if margin < 0:
            return _lost()
        return _void()  # push

    # ── Totals (over/under puntos totales) ──
    total = match.total_points
    if total is None:
        total = ph + pa

    if bt.startswith("total_points_over_"):
        line = _parse_line(bt, "total_points_over_")
        if line is None:
            return (None, None)
        if total > line:
            return _won(pick)
        if total < line:
            return _lost()
        return _void()  # push (linea entera == total)

    if bt.startswith("total_points_under_"):
        line = _parse_line(bt, "total_points_under_")
        if line is None:
            return (None, None)
        if total < line:
            return _won(pick)
        if total > line:
            return _lost()
        return _void()  # push

    return (None, None)


def resolve_user_bets(db: Session, match: Match) -> int:
    """Liquida las user_bets asociadas a los picks resueltos del partido."""
    picks = db.query(Pick).filter(
        Pick.match_id == match.id,
        Pick.result.isnot(None),
    ).all()

    if not picks:
        return 0

    pick_map = {p.id: p for p in picks}
    bets = db.query(UserBet).filter(
        UserBet.match_id == match.id,
        UserBet.result.is_(None),
    ).all()

    resolved = 0
    now = datetime.now(timezone.utc)

    for bet in bets:
        pick = pick_map.get(bet.pick_id)
        if not pick or not pick.result:
            continue

        bet.result = pick.result
        bet.resolved_at = now

        if bet.result == "won":
            bet.profit = round((bet.stake or 0.0) * ((bet.odds or 1.0) - 1.0), 2)
        elif bet.result == "lost":
            bet.profit = -(bet.stake or 0.0)
        else:  # void
            bet.profit = 0.0

        resolved += 1

    if resolved > 0:
        db.commit()

    return resolved


# ──────────────────────────────────────────────────────────────
# Aplicar resultado a un Match
# ──────────────────────────────────────────────────────────────

def apply_final_score(db: Session, match: Match, parsed: dict) -> int:
    """Aplica un marcador final parseado a un Match y liquida sus picks.

    `parsed` admite las claves:
        points_home, points_away (obligatorias),
        total_points (opcional, se deriva si falta),
        is_overtime (opcional), overtimes (opcional),
        score (opcional, se deriva si falta).

    Returns: 1 si se aplico/resolvio, 0 si ya estaba completado.
    """
    if match.is_completed:
        return 0

    ph = parsed["points_home"]
    pa = parsed["points_away"]

    match.points_home = ph
    match.points_away = pa
    match.total_points = parsed.get("total_points", ph + pa)
    match.score = parsed.get("score") or f"{ph}-{pa}"
    if parsed.get("is_overtime") is not None:
        match.is_overtime = bool(parsed["is_overtime"])
    if parsed.get("overtimes") is not None:
        match.overtimes = parsed["overtimes"]
    match.is_completed = True
    match.is_live = False
    match.is_postponed = False
    match.completed_at = datetime.now(timezone.utc)

    n = resolve_match_picks(db, match)

    # Notificacion de resultados (best-effort; no romper la liquidacion).
    _notify_resolved(db, match)

    logger.info(
        f"Resuelto: {match.home_team} {ph}-{pa} {match.away_team} "
        f"| {n} picks | {'OT' if match.is_overtime else 'FT'}"
    )
    return 1


def void_postponed_match(db: Session, match: Match, force: bool = False) -> int:
    """Marca un partido como aplazado/cancelado y voida todos sus picks.

    Guarda de 72h: si el partido es reciente (commence_time + 72h aun no ha
    pasado) devuelve 0 y lo deja pendiente — los aplazados suelen rejugarse
    1-2 dias despues. `force=True` salta la guarda (uso manual/admin).

    Returns: 1 si se proceso, 0 si se aplazo la decision.
    """
    if not force and match.commence_time is not None:
        ct = match.commence_time
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < ct + timedelta(hours=POSTPONED_GUARD_HOURS):
            logger.info(
                f"Postponed guard {POSTPONED_GUARD_HOURS}h: "
                f"{match.home_team} vs {match.away_team} — dejando pendiente"
            )
            return 0

    match.is_postponed = True
    match.is_completed = True
    match.is_live = False
    match.completed_at = datetime.now(timezone.utc)

    picks = db.query(Pick).filter(
        Pick.match_id == match.id,
        Pick.result.is_(None),
    ).all()

    now = datetime.now(timezone.utc)
    for pick in picks:
        pick.result = "void"
        pick.profit_units = 0.0
        pick.resolved_at = now
        pick.is_active = False

    resolve_user_bets(db, match)
    _notify_resolved(db, match)

    if picks:
        logger.info(
            f"APLAZADO/CANCELADO: {match.home_team} vs {match.away_team} "
            f"| {len(picks)} picks -> VOID"
        )
    return 1


def _notify_resolved(db: Session, match: Match) -> None:
    """Envia notificacion Telegram de los picks resueltos (best-effort)."""
    try:
        from app.services.notification_service import send_result
        resolved_picks = db.query(Pick).filter(
            Pick.match_id == match.id,
            Pick.result.in_(["won", "lost", "void"]),
        ).all()
        for rp in resolved_picks:
            send_result(rp, match)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# Fetch de resultados (Basketball Scores API / BetsAPI)
# ──────────────────────────────────────────────────────────────

def _parse_betsapi_event(event: dict) -> Optional[dict]:
    """Parsea un evento de BetsAPI a nuestro formato de marcador final.

    BetsAPI devuelve para basket:
      - event["time_status"]: "3"=ended, "4"=cancelled, "5"=postponed,
                              "0"=not started, "1"=inplay, "2"=suspended.
      - event["ss"]: marcador final "112-104".
      - event["scores"]: desglose por cuartos (clave por periodo); util para
        detectar prorroga (mas periodos de los esperados).

    Returns dict con points_home/away/total_points/score/is_overtime/overtimes,
    o None si el evento no esta terminado o no trae marcador.
    """
    try:
        ts = str(event.get("time_status", ""))
        if ts != "3":
            return None

        ss = event.get("ss")
        parsed = parse_basketball_score(ss) if ss else None
        if not parsed:
            return None

        # Deteccion de prorroga desde el desglose por periodos, si existe.
        # NBA/FIBA = 4 cuartos reglamentarios; >4 periodos -> hubo OT(s).
        is_overtime = None
        overtimes = None
        scores = event.get("scores")
        if isinstance(scores, dict) and scores:
            periods = len(scores)
            if periods > 4:
                is_overtime = True
                overtimes = periods - 4
            elif periods > 0:
                is_overtime = False
                overtimes = 0

        parsed["is_overtime"] = is_overtime
        parsed["overtimes"] = overtimes
        return parsed

    except Exception as e:
        logger.debug(f"BetsAPI parse error: {e}")
        return None


def _fetch_betsapi_event_detail(event_id: str) -> Optional[dict]:
    """Fetch del detalle de un evento concreto en BetsAPI."""
    token = settings.BETSAPI_TOKEN
    if not token:
        return None

    url = f"{BETSAPI_BASE}/event/view"
    params = {"token": token, "event_id": event_id}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params)
        if resp.status_code == 429:
            return None
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") and data.get("results"):
            results = data["results"]
            return results[0] if isinstance(results, list) else results
        return None
    except Exception as e:
        logger.debug(f"BetsAPI fetch error: {e}")
        return None


def fetch_final_score(match: Match) -> Optional[dict]:
    """Obtiene el marcador final de un partido desde las fuentes disponibles.

    Devuelve uno de:
      - dict de marcador final (ver parse_basketball_score / _parse_betsapi_event)
      - {"postponed": True}  si la fuente indica aplazado/cancelado
      - None  si no hay resultado todavia (dejar pendiente)

    Cascada de fuentes:
      1. BetsAPI (event/view) para matches con external_id "betsapi_*".
      2. TODO: Basketball Scores API (API-Basketball) para el resto.
    """
    ext = match.external_id or ""

    # ── Fuente 1: BetsAPI (lookup directo por event_id) ──
    if ext.startswith("betsapi_"):
        event_id = ext.replace("betsapi_", "")
        event = _fetch_betsapi_event_detail(event_id)
        if event:
            ts = str(event.get("time_status", ""))
            if ts in ("4", "5"):
                return {"postponed": True}
            parsed = _parse_betsapi_event(event)
            if parsed:
                return parsed
        return None

    # ── Fuente 2: Basketball Scores API (API-Basketball u otro proveedor) ──
    # TODO: implementar la llamada HTTP real al endpoint de resultados.
    #
    # Una vez confirmado el proveedor (settings.BASKETBALL_SCORES_API_BASE_URL /
    # settings.BASKETBALL_SCORES_API_KEY), realizar un GET por fecha o por
    # game id, localizar el partido (match.external_id o nombres de equipos +
    # commence_time) y devolver el dict normalizado. Esqueleto:
    #
    #   url = settings.BASKETBALL_SCORES_API_BASE_URL.rstrip("/") + "/games"
    #   headers = {"x-apisports-key": settings.BASKETBALL_SCORES_API_KEY}
    #   params = {"date": match.commence_time.strftime("%Y-%m-%d")}
    #   resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
    #   game = _find_game_in_response(resp.json(), match)
    #   if game is "Postponed"/"Cancelled": return {"postponed": True}
    #   if game finished:
    #       return {"points_home": h, "points_away": a, "total_points": h + a,
    #               "score": f"{h}-{a}", "is_overtime": ot, "overtimes": n}
    #   return None
    #
    # La logica de PARSING y LIQUIDACION (apply_final_score / resolve_match_picks)
    # ya esta completa: en cuanto fetch_final_score devuelva un dict valido todo
    # el flujo funciona sin mas cambios.
    logger.debug(
        f"fetch_final_score: sin fuente para external_id={ext} "
        f"({match.home_team} vs {match.away_team}) — TODO Basketball Scores API"
    )
    return None


# ──────────────────────────────────────────────────────────────
# Fuente principal: The Odds API /scores (mismo event id que /odds)
# ──────────────────────────────────────────────────────────────

def _hubo_fallo_desde_inicio(match: Match) -> bool:
    """True si /scores ha fallado en esta liga despues de empezar el partido."""
    fallo = _ULTIMO_FALLO_SCORES.get(match.sport_key)
    if fallo is None or match.commence_time is None:
        return False
    ct = match.commence_time
    if ct.tzinfo is None:
        ct = ct.replace(tzinfo=timezone.utc)
    return fallo >= ct


def _fetch_odds_api_scores(sport_key: str, days_from: int = 3) -> Optional[dict]:
    """Marcadores finales de The Odds API (/scores).

    Endpoint barato (1-2 creditos por llamada, no por partido) que usa la MISMA
    clave que /odds y devuelve el MISMO event id, asi que casa directo con
    match.external_id sin tener que re-emparejar por nombres.

    Returns {event_id: dict_marcador} SOLO para partidos completados, o None si la
    consulta ha fallado (cupo agotado, clave, red): entonces no se sabe nada y el
    llamador NO debe tratar los partidos como "sin resultado".
    """
    if not settings.ODDS_API_KEY or not sport_key:
        _ULTIMO_FALLO_SCORES[sport_key] = datetime.now(timezone.utc)
        return None
    url = f"{settings.ODDS_API_BASE_URL}/sports/{sport_key}/scores"
    params = {"apiKey": settings.ODDS_API_KEY, "daysFrom": days_from}
    out = {}
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, params=params)
        if not resp.is_success:
            motivo = describir_401(resp) if resp.status_code == 401 else f"HTTP {resp.status_code}"
            logger.warning(f"/scores {sport_key}: {motivo}")
            _ULTIMO_FALLO_SCORES[sport_key] = datetime.now(timezone.utc)
            return None
        for ev in resp.json():
            if not ev.get("completed"):
                continue
            home_name = ev.get("home_team")
            away_name = ev.get("away_team")
            ph = pa = None
            for s in ev.get("scores") or []:
                try:
                    val = int(s.get("score"))
                except (TypeError, ValueError):
                    continue
                if s.get("name") == home_name:
                    ph = val
                elif s.get("name") == away_name:
                    pa = val
            if ph is None or pa is None:
                continue
            out[ev["id"]] = {
                "points_home": ph,
                "points_away": pa,
                "total_points": ph + pa,
                "score": f"{ph}-{pa}",
                "is_overtime": None,   # The Odds API no da desglose por cuartos
                "overtimes": None,
            }
        return out
    except Exception as e:
        logger.warning(f"Odds API /scores error para {sport_key}: {e}")
        _ULTIMO_FALLO_SCORES[sport_key] = datetime.now(timezone.utc)
        return None


# ──────────────────────────────────────────────────────────────
# Entrada publica (la llama el scheduler)
# ──────────────────────────────────────────────────────────────

def resolve_completed(db: Session) -> int:
    """Resuelve partidos terminados y liquida sus picks.

    Busca matches pasados de commence_time aun no completados, obtiene su
    marcador final y los liquida. Devuelve el numero de partidos resueltos.

    Fuentes:
      - The Odds API /scores (principal): para eventos de The Odds API. Se pide
        UNA vez por liga y se cachea en este ciclo (no una llamada por partido).
      - BetsAPI (fallback): para eventos con external_id "betsapi_*".
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=STALE_AFTER_HOURS)

    stale = db.query(Match).filter(
        Match.is_completed == False,
        Match.commence_time < cutoff,
    ).all()

    if not stale:
        return 0

    # Prefetch de scores por liga (una llamada por sport_key de eventos no-betsapi)
    sport_keys = {
        m.sport_key for m in stale
        if m.sport_key and not (m.external_id or "").startswith("betsapi_")
    }
    scores_maps = {sk: _fetch_odds_api_scores(sk) for sk in sport_keys}

    resolved_count = 0

    for match in stale:
        ext = match.external_id or ""
        try:
            if ext.startswith("betsapi_"):
                result = fetch_final_score(match)            # BetsAPI fallback
            else:
                mapa = scores_maps.get(match.sport_key, {})
                if mapa is None:
                    continue        # la consulta ha fallado: el partido sigue pendiente
                result = mapa.get(ext)
        except Exception as e:
            logger.error(
                f"fetch score fallo para "
                f"{match.home_team} vs {match.away_team}: {e}"
            )
            continue

        if result is None:
            if not ext.startswith("betsapi_") and _hubo_fallo_desde_inicio(match):
                logger.info(
                    f"Sin resultado de {match.home_team} vs {match.away_team}, pero /scores ha "
                    f"fallado desde que empezo: no se anula"
                )
                continue
            # Sin resultado: si lleva demasiado tiempo sin completarse, evaluar
            # aplazamiento (con guarda de 72h dentro de void_postponed_match).
            resolved_count += void_postponed_match(db, match)
            continue

        if result.get("postponed"):
            resolved_count += void_postponed_match(db, match)
            continue

        resolved_count += apply_final_score(db, match, result)

    if resolved_count > 0:
        db.commit()
        logger.info(
            f"resolve_completed: {resolved_count} partidos resueltos "
            f"de {len(stale)} stale"
        )

    return resolved_count
