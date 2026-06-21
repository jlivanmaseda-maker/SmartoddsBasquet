"""BetsAPI Odds Fetcher — ligas de basket FUERA de The Odds API.

The Odds API ya cubre NBA / EuroLeague / NCAA / WNBA. Este modulo SOLO sirve
para ligas extra (arrancamos con la ACB espanola) via BetsAPI, que expone odds
pre-match para competiciones que The Odds API no incluye.

Routing critico de scores: el external_id se prefija "betsapi_" + event_id de
BetsAPI. Asi el score_resolver enruta estos partidos a su path de fallback
BetsAPI. NO cambiar el prefijo sin tocar el resolver.

Endpoints:
- /v1/events/upcoming?sport_id=18 — proximos partidos de basket (info basica)
- /v1/event/odds?event_id=X       — odds pre-match por mercado (time-series)

Mercados de basket en BetsAPI (`results.odds`, claves numericas):
- 18_1 = money line (home_od / away_od)        -> odds_home / odds_away
- 18_2 = spread / handicap (handicap, home_od, away_od)
                                               -> spread_line / odds_spread_*
- 18_3 = over/under totals (handicap = linea, over_od / under_od)
                                               -> total_line / odds_over / odds_under

Rate limit: Volume One plan compartido (199,999 req/hour). Por ciclo gastamos
pocas decenas de req (solo ligas filtradas).
"""
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from app.config import settings
from app.db.database import SessionLocal
from app.models.match import Match
from app.models.odds import Odds, OddsHistory
# Reutilizamos el helper de matching/alias de equipos para mantener consistencia
# con el odds_fetcher de The Odds API (NO duplicar la logica de alias).
from app.services.odds_fetcher import _find_or_create_team

logger = logging.getLogger("smartodds_basketball.betsapi")

BETSAPI_BASE = "https://api.b365api.com/v1"

# Pausa entre llamadas /event/odds para no martillear la API (cortesia, aunque
# el plan tiene cupo de sobra).
_ODDS_REQUEST_DELAY_S = 0.10


# ──────────────────────────────────────────────────────────────
# Clasificacion de liga (filtro INCLUDE + league_tier)
# ──────────────────────────────────────────────────────────────

def _league_included(league_name: str) -> bool:
    """True si el nombre de liga contiene (case-insensitive) algun substring
    de settings.BETSAPI_LEAGUES. Solo procesamos ligas EXTRA (ACB, etc.)."""
    if not league_name:
        return False
    lname = league_name.lower()
    for sub in settings.BETSAPI_LEAGUES:
        sub = sub.strip().lower()
        if sub and sub in lname:
            return True
    return False


def _slug(text: str) -> str:
    """Slug simple para usar como league_tier por defecto."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "betsapi"


def _league_tier(league_name: str) -> str:
    """Deriva league_tier mirando settings.BETSAPI_LEAGUE_TIER_MAP por substring.

    Si ningun substring casa, usa un slug del nombre de liga (default seguro)."""
    lname = league_name.lower()
    for sub, tier in settings.BETSAPI_LEAGUE_TIER_MAP.items():
        if sub.lower() in lname:
            return tier
    return _slug(league_name)


# ──────────────────────────────────────────────────────────────
# Llamadas a la API
# ──────────────────────────────────────────────────────────────

def _fetch_upcoming_events(page: int = 1) -> tuple[list, int]:
    """Fetch de proximos partidos de basket. Returns (events, total_pages)."""
    token = settings.BETSAPI_TOKEN
    if not token:
        return [], 0

    url = f"{BETSAPI_BASE}/events/upcoming"
    params = {
        "sport_id": settings.BETSAPI_BASKETBALL_SPORT_ID,
        "token": token,
        "page": page,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)

        if resp.status_code == 429:
            logger.warning("BetsAPI: rate limit en upcoming events")
            return [], 0
        resp.raise_for_status()

        data = resp.json()
        if not data.get("success"):
            logger.warning(f"BetsAPI upcoming error: {data.get('error', 'unknown')}")
            return [], 0

        events = data.get("results", [])
        pager = data.get("pager", {})
        total = int(pager.get("total", 0))
        per_page = int(pager.get("per_page", 50))
        total_pages = (
            (total // per_page) + (1 if total % per_page else 0)
            if per_page > 0 else 0
        )
        return events, total_pages

    except Exception as e:
        logger.error(f"BetsAPI upcoming fetch error: {e}")
        return [], 0


def _fetch_event_odds(event_id: str) -> dict:
    """Fetch de odds de un evento. Returns dict de mercados parseados.

    Returns:
        {
            "bookmaker": "betsapi" | "bet365",
            "odds_home": float|None, "odds_away": float|None,
            "spread_line": float|None, "odds_spread_home": float|None,
            "odds_spread_away": float|None,
            "total_line": float|None, "odds_over": float|None,
            "odds_under": float|None,
        }
        o {} si no hay odds.
    """
    token = settings.BETSAPI_TOKEN
    if not token:
        return {}

    url = f"{BETSAPI_BASE}/event/odds"
    params = {"token": token, "event_id": event_id}

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)

        if resp.status_code == 429:
            logger.warning("BetsAPI: rate limit en event odds")
            return {}
        resp.raise_for_status()

        data = resp.json()
        if not data.get("success"):
            return {}

        results = data.get("results", {}) or {}
        return _parse_betsapi_odds(results)

    except Exception as e:
        logger.debug(f"BetsAPI odds fetch error for {event_id}: {e}")
        return {}


def _to_float(val) -> Optional[float]:
    """Convierte un string de cuota a float (None si invalido o <= 1.0)."""
    if val in (None, "", "-"):
        return None
    try:
        f = float(val)
    except (ValueError, TypeError):
        return None
    return f if f > 1.0 else None


def _latest_entry(market) -> Optional[dict]:
    """BetsAPI devuelve una time-series (lista) por mercado; tomamos la mas
    reciente. La API ordena de mas nuevo a mas viejo, asi que el primer dict
    valido es el actual. Tolera tambien que venga ya como dict suelto."""
    if isinstance(market, dict):
        return market
    if isinstance(market, list):
        for entry in market:  # primero = mas reciente en /event/odds
            if isinstance(entry, dict):
                return entry
    return None


def _parse_betsapi_odds(results: dict) -> dict:
    """Parsea results["odds"] de /v1/event/odds para basket.

    Estructura esperada (sport_id=18):
        results["odds"] = {
            "18_1": [ {"home_od": "1.80", "away_od": "2.00", "add_time": ...}, ... ],
            "18_2": [ {"handicap": "-3.5", "home_od": "1.90", "away_od": "1.90"}, ...],
            "18_3": [ {"handicap": "165.5", "over_od": "1.90", "under_od": "1.90"}, ...],
        }
    BetsAPI sirve una sola fuente de odds (bet365 en la mayoria de planes). La
    etiquetamos "bet365" si el bloque lo indica, si no "betsapi".
    """
    odds_block = results.get("odds")
    if not isinstance(odds_block, dict):
        return {}

    out: dict = {}

    # Money line (18_1) — imprescindible para tener un pick activo
    ml = _latest_entry(odds_block.get(f"{settings.BETSAPI_BASKETBALL_SPORT_ID}_1"))
    if ml:
        out["odds_home"] = _to_float(ml.get("home_od"))
        out["odds_away"] = _to_float(ml.get("away_od"))

    # Spread / handicap (18_2)
    sp = _latest_entry(odds_block.get(f"{settings.BETSAPI_BASKETBALL_SPORT_ID}_2"))
    if sp:
        try:
            hcap = sp.get("handicap")
            out["spread_line"] = float(hcap) if hcap not in (None, "", "-") else None
        except (ValueError, TypeError):
            out["spread_line"] = None
        out["odds_spread_home"] = _to_float(sp.get("home_od"))
        out["odds_spread_away"] = _to_float(sp.get("away_od"))

    # Over/Under totals (18_3) — handicap = linea de puntos
    tot = _latest_entry(odds_block.get(f"{settings.BETSAPI_BASKETBALL_SPORT_ID}_3"))
    if tot:
        try:
            line = tot.get("handicap")
            out["total_line"] = float(line) if line not in (None, "", "-") else None
        except (ValueError, TypeError):
            out["total_line"] = None
        out["odds_over"] = _to_float(tot.get("over_od"))
        out["odds_under"] = _to_float(tot.get("under_od"))

    # Si no hay ningun mercado util, devolvemos vacio.
    if not any(v is not None for v in out.values()):
        return {}

    # Bookmaker label: BetsAPI suele exponer bet365 como fuente. Si el bloque
    # trae una pista explicita de fuente, usala; si no, "betsapi".
    # TODO: confirmar con respuesta real si /event/odds incluye un campo de
    # bookmaker para basket. De momento etiquetamos "betsapi".
    out["bookmaker"] = "betsapi"
    return out


# ──────────────────────────────────────────────────────────────
# Procesamiento por evento
# ──────────────────────────────────────────────────────────────

def _process_event(db, event, stats) -> None:
    """Procesa 1 evento BetsAPI: upsert Match + Teams + Odds.

    Pensado para correr dentro de un try/except del caller; un fallo aqui no
    aborta el lote. NO hace commit (lo hace fetch_all)."""
    betsapi_id = str(event.get("id", ""))
    if not betsapi_id:
        return

    league = event.get("league", {}) or {}
    league_name = league.get("name", "") or ""
    if not _league_included(league_name):
        return

    home_name = (event.get("home", {}) or {}).get("name", "")
    away_name = (event.get("away", {}) or {}).get("name", "")
    if not home_name or not away_name:
        return

    # commence_time: BetsAPI usa unix timestamp (campo "time")
    time_val = event.get("time")
    if not time_val:
        return
    try:
        commence_time = datetime.fromtimestamp(int(time_val), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return

    # Saltar partidos ya empezados (>1h) o demasiado lejanos (>7d)
    now = datetime.now(timezone.utc)
    if commence_time < now - timedelta(hours=1):
        return
    if commence_time > now + timedelta(days=7):
        return

    external_id = f"betsapi_{betsapi_id}"
    league_tier = _league_tier(league_name)
    stats.setdefault("leagues", set()).add(league_name)

    # ---- Match (upsert por external_id) ----
    match = db.query(Match).filter(Match.external_id == external_id).first()
    if not match:
        home_team = _find_or_create_team(db, home_name, league_tier)
        away_team = _find_or_create_team(db, away_name, league_tier)

        match = Match(
            external_id=external_id,
            sport_key="betsapi_basketball",
            league=league_name,
            league_tier=league_tier,
            home_team=home_name,
            away_team=away_name,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            commence_time=commence_time,
        )
        db.add(match)
        db.flush()
        stats["matches"] += 1
        logger.debug(f"Nuevo match BetsAPI: {home_name} vs {away_name} ({league_name})")

    # ---- Odds ----
    time.sleep(_ODDS_REQUEST_DELAY_S)  # cortesia rate-limit
    odds_data = _fetch_event_odds(betsapi_id)
    if not odds_data:
        return

    bookmaker = odds_data.get("bookmaker", "betsapi")

    odds_fields = {
        "odds_home": odds_data.get("odds_home"),
        "odds_away": odds_data.get("odds_away"),
        "spread_line": odds_data.get("spread_line"),
        "odds_spread_home": odds_data.get("odds_spread_home"),
        "odds_spread_away": odds_data.get("odds_spread_away"),
        "total_line": odds_data.get("total_line"),
        "odds_over": odds_data.get("odds_over"),
        "odds_under": odds_data.get("odds_under"),
        "last_updated": datetime.now(timezone.utc),
    }

    # Upsert Odds (unico por match_id + bookmaker), mismo patron que odds_fetcher
    odds = db.query(Odds).filter(
        Odds.match_id == match.id,
        Odds.bookmaker == bookmaker,
    ).first()

    if odds:
        for k, v in odds_fields.items():
            if v is not None:
                setattr(odds, k, v)
    else:
        odds = Odds(
            match_id=match.id,
            bookmaker=bookmaker,
            **{k: v for k, v in odds_fields.items() if v is not None},
        )
        db.add(odds)

    # OddsHistory snapshot
    history = OddsHistory(
        match_id=match.id,
        bookmaker=bookmaker,
        odds_home=odds_data.get("odds_home"),
        odds_away=odds_data.get("odds_away"),
        spread_line=odds_data.get("spread_line"),
        odds_spread_home=odds_data.get("odds_spread_home"),
        odds_spread_away=odds_data.get("odds_spread_away"),
        total_line=odds_data.get("total_line"),
        odds_over=odds_data.get("odds_over"),
        odds_under=odds_data.get("odds_under"),
    )
    db.add(history)
    stats["odds"] += 1


# ──────────────────────────────────────────────────────────────
# Entrypoint publico (lo llama el scheduler)
# ──────────────────────────────────────────────────────────────

def fetch_all(db=None) -> dict:
    """Ingiere odds de ligas de basket EXTRA (no cubiertas por The Odds API)
    via BetsAPI. Arrancamos con la ACB; ampliar via settings.BETSAPI_LEAGUES.

    Si la ingesta esta desactivada o no hay token, devuelve {"skipped":"disabled"}
    sin tocar la BD. El scheduler puede pasar una sesion `db`; si no, se abre
    una propia.

    Returns:
        {
            "matches": N,            # nuevos matches creados
            "odds": M,               # filas de odds upsert
            "leagues": [...],        # nombres de liga procesados
            "errors": E,
        }
    """
    if not settings.BETSAPI_ODDS_ENABLED or not settings.BETSAPI_TOKEN:
        logger.debug("BetsAPI odds deshabilitado o sin token, skip")
        return {"skipped": "disabled"}

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    stats = {"matches": 0, "odds": 0, "errors": 0, "leagues": set()}

    try:
        # Paso 1: listar proximos partidos (hasta 10 paginas ~ 500 eventos)
        all_events = []
        for page in range(1, 11):
            events, total_pages = _fetch_upcoming_events(page)
            if not events:
                break
            all_events.extend(events)
            if page >= total_pages:
                break

        logger.debug(f"BetsAPI: {len(all_events)} eventos de basket escaneados")

        # Paso 2/3: filtrar por liga y procesar (try/except por evento para que
        # un evento malo NUNCA aborte el lote)
        for event in all_events:
            try:
                _process_event(db, event, stats)
            except Exception as e:
                logger.error(
                    f"Error procesando evento BetsAPI {event.get('id', '?')}: {e}",
                    exc_info=True,
                )
                stats["errors"] += 1

        db.commit()
        logger.info(
            f"BetsAPI odds: {stats['matches']} nuevos matches, "
            f"{stats['odds']} odds, "
            f"{len(stats['leagues'])} ligas, "
            f"{stats['errors']} errores"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"BetsAPI fetch_all error: {e}", exc_info=True)
        stats["errors"] += 1
    finally:
        if owns_session:
            db.close()

    # Convertimos el set de ligas a lista para el resumen serializable
    stats["leagues"] = sorted(stats["leagues"])
    return stats
