"""Odds Fetcher — The Odds API para basket (NBA/EuroLeague/NCAA/WNBA).

Fetch de cuotas para todas las ligas monitorizadas.
Crea/actualiza Match, Odds, OddsHistory y vincula Teams.

The Odds API response format (basket, igual estructura que tenis/futbol):
[{
    "id": "abc123",
    "sport_key": "basketball_nba",
    "sport_title": "NBA",
    "commence_time": "2026-01-15T00:00:00Z",
    "home_team": "Los Angeles Lakers",
    "away_team": "Boston Celtics",
    "bookmakers": [{
        "key": "pinnacle",
        "markets": [{
            "key": "h2h",
            "outcomes": [
                {"name": "Los Angeles Lakers", "price": 1.85},
                {"name": "Boston Celtics", "price": 2.05}
            ]
        }]
    }]
}]

NOTA: este fichero es SOLO The Odds API (external_id = event id crudo).
Los ids de BetsAPI se prefijan "betsapi_" en su propio fetcher.
"""
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.db.database import SessionLocal
from app.models.match import Match
from app.models.team import Team, TeamNameAlias
from app.models.odds import Odds, OddsHistory

logger = logging.getLogger("smartodds_basketball.odds_fetcher")

# Mapping sport_key -> liga display name (keys reales de The Odds API)
SPORT_KEY_NAMES = {
    "basketball_nba": "NBA",
    "basketball_nba_preseason": "NBA Preseason",
    "basketball_wnba": "WNBA",
    "basketball_ncaab": "NCAA Basketball",
    "basketball_ncaab_championship_winner": "NCAA Championship",
    "basketball_euroleague": "EuroLeague",
    "basketball_nbl": "NBL Australia",
}

# Mapping sport_key -> league_tier (corto, para filtros/modelo)
SPORT_KEY_TIER = {
    "basketball_nba": "nba",
    "basketball_nba_preseason": "nba",
    "basketball_wnba": "wnba",
    "basketball_ncaab": "ncaab",
    "basketball_ncaab_championship_winner": "ncaab",
    "basketball_euroleague": "euroleague",
    "basketball_nbl": "nbl",
}

# Exchanges excluidos: cuotas infladas (no incluyen comision ~2-5%)
EXCHANGE_BOOKMAKERS = {"betfair_ex_eu", "betfair_ex_uk", "matchbook", "smarkets"}


def _league_name(sport_key: str) -> str:
    """Nombre legible de la liga a partir del sport_key."""
    return SPORT_KEY_NAMES.get(sport_key, sport_key)


def _league_tier(sport_key: str) -> str:
    """Tier corto de la liga (nba/euroleague/ncaab/wnba/...)."""
    return SPORT_KEY_TIER.get(sport_key, sport_key.replace("basketball_", ""))


def _find_or_create_team(db, name: str, league: str) -> Team:
    """Busca equipo por nombre o alias. Crea si no existe.

    Reusa el enfoque de alias de tenis (PlayerNameAlias -> TeamNameAlias).
    El alias es UNICO GLOBAL: si el nombre ya es alias de otro equipo, NO se
    reinserta (evita UniqueViolation que haria rollback del ciclo entero).
    """
    # Buscar por nombre exacto
    team = db.query(Team).filter(Team.name == name).first()
    if team:
        return team

    # Buscar por alias
    alias = db.query(TeamNameAlias).filter(TeamNameAlias.alias == name).first()
    if alias:
        team = db.query(Team).filter(Team.id == alias.team_id).first()
        if team:
            return team

    # Crear nuevo equipo
    team = Team(name=name, league=league)
    db.add(team)
    db.flush()

    # Registrar alias solo si NO existe ya (ix unico global sobre alias)
    if alias is None:
        db.add(TeamNameAlias(
            team_id=team.id,
            alias=name,
            source="odds_api",
        ))
        db.flush()

    logger.info(f"Nuevo equipo creado: {name} (league={league}, id={team.id})")
    return team


def _parse_outcomes(bookmaker_data: dict, market_key: str, home_name: str, away_name: str) -> dict:
    """Extrae outcomes de un mercado para un bookmaker.

    Returns dict con las cuotas parseadas.

    Mercados basket en The Odds API:
      - h2h     -> moneyline 2 vias (odds_home/odds_away)
      - totals  -> over/under puntos (total_line/odds_over/odds_under)
      - spreads -> handicap de puntos (spread_line/odds_spread_home/odds_spread_away)
    """
    result = {}
    for market in bookmaker_data.get("markets", []):
        if market["key"] != market_key:
            continue
        for outcome in market.get("outcomes", []):
            name = outcome.get("name", "")
            price = outcome.get("price")
            point = outcome.get("point")

            if market_key == "h2h":
                if name == home_name:
                    result["odds_home"] = price
                elif name == away_name:
                    result["odds_away"] = price

            elif market_key == "totals":
                if point is not None:
                    result["total_line"] = point
                if name == "Over":
                    result["odds_over"] = price
                elif name == "Under":
                    result["odds_under"] = price

            elif market_key == "spreads":
                # spread_line se referencia al local (handicap de puntos del home)
                if name == home_name and point is not None:
                    result["spread_line"] = point
                    result["odds_spread_home"] = price
                elif name == away_name and point is not None:
                    result["odds_spread_away"] = price

    return result


def fetch_active_basketball_keys() -> set:
    """Ligas de basket ACTIVAS segun The Odds API.

    El endpoint /sports es GRATIS (no consume cupo). Devuelve el set de
    sport_keys de basket con active=true, para no gastar creditos pidiendo
    odds de ligas fuera de temporada (NBA/EuroLeague/NCAA en verano, etc.).
    Si la llamada falla, devuelve None -> el caller hace fetch de todas.
    """
    if not settings.ODDS_API_KEY:
        return None
    url = f"{settings.ODDS_API_BASE_URL}/sports"
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, params={"apiKey": settings.ODDS_API_KEY})
        if not resp.is_success:
            return None
        active = {
            s["key"] for s in resp.json()
            if s.get("active") and str(s.get("key", "")).startswith("basketball_")
        }
        return active
    except Exception as e:
        logger.warning(f"No se pudo consultar /sports (fetch de todas): {e}")
        return None


def fetch_league_odds(sport_key: str) -> list:
    """Fetch odds de The Odds API para una liga.

    Returns lista de eventos con bookmakers y cuotas.
    """
    if not settings.ODDS_API_KEY:
        logger.warning("ODDS_API_KEY no configurada, skip fetch")
        return []

    url = f"{settings.ODDS_API_BASE_URL}/sports/{sport_key}/odds"
    params = {
        "apiKey": settings.ODDS_API_KEY,
        "regions": settings.ODDS_API_REGIONS,
        "markets": settings.ODDS_API_MARKETS,
        "oddsFormat": "decimal",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)

        if resp.status_code == 404:
            # Liga no activa en este momento
            return []
        if resp.status_code == 422:
            logger.debug(f"{sport_key}: sin eventos activos (422)")
            return []
        if resp.status_code == 401:
            logger.error("ODDS_API_KEY invalida o expirada")
            return []

        resp.raise_for_status()

        # Log remaining credits
        remaining = resp.headers.get("x-requests-remaining")
        used = resp.headers.get("x-requests-used")
        if remaining:
            logger.debug(f"Odds API credits: {remaining} remaining, {used} used")

        events = resp.json()
        logger.info(f"{sport_key}: {len(events)} eventos con cuotas")
        return events

    except httpx.TimeoutException:
        logger.error(f"Timeout fetching {sport_key}")
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {sport_key}: {e.response.status_code}")
        return []
    except Exception as e:
        logger.error(f"Error fetching {sport_key}: {e}", exc_info=True)
        return []


def process_league_events(db, sport_key: str, events: list) -> dict:
    """Procesa eventos de una liga: crea/actualiza Match, Odds, OddsHistory, Teams.

    Returns dict con contadores.
    """
    stats = {"new_matches": 0, "updated_odds": 0, "errors": 0}
    if not events:
        return stats

    league_name = _league_name(sport_key)
    league_tier = _league_tier(sport_key)

    for event in events:
        try:
            external_id = event["id"]
            home_name = event["home_team"]
            away_name = event["away_team"]
            commence_str = event["commence_time"]
            commence_time = datetime.fromisoformat(
                commence_str.replace("Z", "+00:00")
            )

            # ---- Match ----
            match = db.query(Match).filter(
                Match.external_id == external_id
            ).first()

            if not match:
                # Buscar/crear equipos
                home_team = _find_or_create_team(db, home_name, league_tier)
                away_team = _find_or_create_team(db, away_name, league_tier)

                match = Match(
                    external_id=external_id,
                    sport_key=sport_key,
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
                stats["new_matches"] += 1
                logger.debug(f"Nuevo match: {home_name} vs {away_name} ({league_name})")

            # ---- Odds por bookmaker ----
            for bk_data in event.get("bookmakers", []):
                bk_key = bk_data["key"]
                if bk_key in EXCHANGE_BOOKMAKERS:
                    continue

                # Parsear mercados
                h2h = _parse_outcomes(bk_data, "h2h", home_name, away_name)
                totals = _parse_outcomes(bk_data, "totals", home_name, away_name)
                spreads = _parse_outcomes(bk_data, "spreads", home_name, away_name)

                if not h2h.get("odds_home"):
                    continue  # Sin h2h no tiene sentido

                # Upsert Odds (unico por match_id + bookmaker)
                odds = db.query(Odds).filter(
                    Odds.match_id == match.id,
                    Odds.bookmaker == bk_key,
                ).first()

                odds_fields = {
                    "odds_home": h2h.get("odds_home"),
                    "odds_away": h2h.get("odds_away"),
                    "total_line": totals.get("total_line"),
                    "odds_over": totals.get("odds_over"),
                    "odds_under": totals.get("odds_under"),
                    "spread_line": spreads.get("spread_line"),
                    "odds_spread_home": spreads.get("odds_spread_home"),
                    "odds_spread_away": spreads.get("odds_spread_away"),
                    "last_updated": datetime.now(timezone.utc),
                }

                if odds:
                    for k, v in odds_fields.items():
                        if v is not None:
                            setattr(odds, k, v)
                else:
                    odds = Odds(
                        match_id=match.id,
                        bookmaker=bk_key,
                        **{k: v for k, v in odds_fields.items() if v is not None},
                    )
                    db.add(odds)

                # OddsHistory snapshot
                history = OddsHistory(
                    match_id=match.id,
                    bookmaker=bk_key,
                    odds_home=h2h.get("odds_home"),
                    odds_away=h2h.get("odds_away"),
                    total_line=totals.get("total_line"),
                    odds_over=totals.get("odds_over"),
                    odds_under=totals.get("odds_under"),
                    spread_line=spreads.get("spread_line"),
                    odds_spread_home=spreads.get("odds_spread_home"),
                    odds_spread_away=spreads.get("odds_spread_away"),
                )
                db.add(history)
                stats["updated_odds"] += 1

        except Exception as e:
            logger.error(f"Error procesando evento {event.get('id', '?')}: {e}", exc_info=True)
            stats["errors"] += 1

    return stats


def fetch_all(db=None) -> dict:
    """Fetch y procesa odds para todas las ligas monitorizadas.

    Loop sobre settings.MONITORED_LEAGUES, descarga cada liga via The Odds API,
    hace upsert de Match + Team + Odds y devuelve un resumen.

    El scheduler pasa una sesion `db`; si no se pasa, se abre una propia.

    Returns:
        {
            "matches": N,           # nuevos matches creados
            "odds": M,              # filas de odds actualizadas/creadas
            "leagues": [...],       # sport_keys procesadas
            "errors": E,
            "active_external_ids": set(...),  # para deteccion de partidos stale
        }
    """
    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    total = {"matches": 0, "odds": 0, "leagues": [], "errors": 0}
    active_external_ids = set()

    monitored = [sk.strip() for sk in settings.MONITORED_LEAGUES if sk.strip()]

    # Filtrar a ligas activas (llamada gratis a /sports) para ahorrar cupo.
    active_keys = fetch_active_basketball_keys()
    if active_keys is not None:
        skipped = [sk for sk in monitored if sk not in active_keys]
        monitored = [sk for sk in monitored if sk in active_keys]
        if skipped:
            logger.info(f"Ligas fuera de temporada omitidas (ahorro de cupo): {skipped}")
        if not monitored:
            logger.info("Ninguna liga monitorizada activa ahora mismo")

    try:
        for sport_key in monitored:
            events = fetch_league_odds(sport_key)
            stats = process_league_events(db, sport_key, events)

            # Track active event IDs for stale match detection
            for e in (events or []):
                eid = e.get("id")
                if eid:
                    active_external_ids.add(eid)

            total["matches"] += stats["new_matches"]
            total["odds"] += stats["updated_odds"]
            total["errors"] += stats["errors"]
            total["leagues"].append(sport_key)

        db.commit()
        logger.info(
            f"Fetch completo: {len(total['leagues'])} ligas, "
            f"{total['matches']} nuevos matches, "
            f"{total['odds']} odds updates, "
            f"{total['errors']} errores, "
            f"{len(active_external_ids)} eventos activos"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error commit fetch_all: {e}", exc_info=True)
        total["errors"] += 1
    finally:
        if owns_session:
            db.close()

    total["active_external_ids"] = active_external_ids
    return total
