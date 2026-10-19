"""Seed de ELO histórico + backtest del modelo (walk-forward).

Fuente de resultados: ESPN scoreboard (endpoint abierto, sin API key):
  https://site.api.espn.com/apis/site/v2/sports/basketball/{league}/scoreboard?dates=YYYYMMDD

Dos usos:
  1. SEED — recorre una temporada en orden cronológico y deja el ELO de cada
     equipo actualizado en la BD (para que el modelo no arranque ciego a 1500).
  2. BACKTEST — además de actualizar, predice CADA partido ANTES de aplicar su
     resultado (walk-forward, sin fuga de información) y acumula métricas:
     accuracy, Brier score y log-loss. Permite grid-search de ELO_HOME_ADVANTAGE
     y K para minimizar log-loss.

NOTA: el seed solo puebla ELO (no net_rating/form), así que el ensemble se
reduce de facto a ELO + ventaja de cancha — la palanca principal de un modelo
de basket v1. La calibración de SYSTEM_MIN_EDGE (edge→ROI) NO se hace aquí:
necesita histórico de cuotas+resultados (acumulación en shadow).
"""
import logging
import math
from datetime import date, timedelta

import httpx

from app.config import settings
from app.db.database import SessionLocal
from app.models.team import Team
from app.services.odds_fetcher import _find_or_create_team

logger = logging.getLogger("smartodds_basketball.elo_seed")

# league_tier interno -> path de ESPN
ESPN_LEAGUE_PATHS = {
    "nba": "nba",
    "wnba": "wnba",
    "ncaab": "mens-college-basketball",
    "euroleague": None,   # ESPN no cubre EuroLeague de forma fiable; TODO otra fuente
}

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball"

# Nombres de ESPN que no coinciden con los de The Odds API (comprobado el
# 19-oct-2026 sobre la NBA 2025-26: solo difiere este). Sin esto el seed crea
# un equipo duplicado y el ELO no llega al equipo de los partidos reales.
ESPN_NAME_FIX = {
    "LA Clippers": "Los Angeles Clippers",
}


def _es_exhibicion(nombre: str) -> bool:
    """Partidos del All-Star / Rising Stars (ESPN los lista como completados):
    "Team Stars", "Team Stripes", "World", "Team LeBron", "USA"... No son
    equipos y no deben entrar en el ELO ni crear equipos en la BD."""
    return nombre.startswith("Team ") or nombre in {"World", "USA", "Stars", "Stripes"}



# ──────────────────────────────────────────────────────────────
# Crawler ESPN
# ──────────────────────────────────────────────────────────────

def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def fetch_espn_day(league_path: str, d: date, client: httpx.Client) -> list:
    """Partidos COMPLETADOS de un día. Devuelve lista de dicts cronológica."""
    url = f"{ESPN_BASE}/{league_path}/scoreboard"
    out = []
    try:
        resp = client.get(url, params={"dates": d.strftime("%Y%m%d")}, timeout=20)
        if not resp.is_success:
            return out
        for ev in resp.json().get("events", []):
            status = ev.get("status", {}).get("type", {})
            if not status.get("completed"):
                continue
            comp = ev.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            home = away = None
            for c in competitors:
                rec = {
                    "name": ESPN_NAME_FIX.get(c["team"]["displayName"], c["team"]["displayName"]),
                    "score": int(c["score"]) if c.get("score") not in (None, "") else None,
                }
                if c.get("homeAway") == "home":
                    home = rec
                elif c.get("homeAway") == "away":
                    away = rec
            if not home or not away or home["score"] is None or away["score"] is None:
                continue
            if _es_exhibicion(home["name"]) or _es_exhibicion(away["name"]):
                continue
            out.append({
                "date": ev.get("date"),
                "home": home["name"], "away": away["name"],
                "home_pts": home["score"], "away_pts": away["score"],
            })
    except Exception as e:
        logger.debug(f"ESPN {league_path} {d}: {e}")
    return out


def crawl_results(league_tier: str, start: date, end: date) -> list:
    """Todos los partidos completados de la liga en [start, end], cronológicos."""
    path = ESPN_LEAGUE_PATHS.get(league_tier)
    if not path:
        raise ValueError(f"Sin fuente ESPN para league_tier={league_tier}")
    games = []
    with httpx.Client(timeout=20) as client:
        for d in _daterange(start, end):
            games.extend(fetch_espn_day(path, d, client))
    logger.info(f"ESPN {league_tier}: {len(games)} partidos en {start}..{end}")
    return games


# ──────────────────────────────────────────────────────────────
# Motor ELO (walk-forward) — autocontenido para poder hacer grid-search
# ──────────────────────────────────────────────────────────────

def _expected(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def walk_forward(games: list, k: float, home_adv: float,
                 mov: bool = True) -> dict:
    """Recorre los partidos, predice antes de actualizar y acumula métricas.

    Returns dict: { 'elos': {team: rating}, 'n', 'accuracy', 'brier', 'logloss' }
    mov=True aplica multiplicador de margen de victoria (recomendado en basket).
    """
    elos = {}
    n = 0
    correct = 0
    brier_sum = 0.0
    logloss_sum = 0.0

    for g in games:
        h, a = g["home"], g["away"]
        eh = elos.get(h, 1500.0)
        ea = elos.get(a, 1500.0)

        # Predicción ANTES de ver el resultado (walk-forward)
        p_home = _expected(eh + home_adv, ea)
        home_won = 1 if g["home_pts"] > g["away_pts"] else 0

        # Métricas (solo cuando ambos equipos ya tienen historia para ser justos)
        if h in elos and a in elos:
            n += 1
            correct += 1 if (p_home >= 0.5) == bool(home_won) else 0
            brier_sum += (p_home - home_won) ** 2
            p = min(max(p_home, 1e-9), 1 - 1e-9)
            logloss_sum += -(home_won * math.log(p) + (1 - home_won) * math.log(1 - p))

        # Actualización de ELO
        margin = abs(g["home_pts"] - g["away_pts"])
        k_eff = k
        if mov:
            # Multiplicador MOV estilo FiveThirtyEight (atenúa el efecto autocorrelación)
            elo_diff = (eh + home_adv) - ea
            k_eff = k * math.log(margin + 1) * (2.2 / ((elo_diff if home_won else -elo_diff) * 0.001 + 2.2))
        delta = k_eff * (home_won - p_home)
        elos[h] = eh + delta
        elos[a] = ea - delta

    return {
        "elos": elos, "n": n,
        "accuracy": correct / n if n else 0.0,
        "brier": brier_sum / n if n else 0.0,
        "logloss": logloss_sum / n if n else 0.0,
    }


def grid_search(games: list) -> dict:
    """Busca (k, home_adv) que minimizan log-loss. Devuelve el mejor + tabla."""
    results = []
    for k in (12, 20, 28, 36):
        for ha in (40, 70, 100, 130):
            m = walk_forward(games, k=k, home_adv=ha)
            results.append({"k": k, "home_adv": ha, **{
                key: m[key] for key in ("n", "accuracy", "brier", "logloss")
            }})
    results.sort(key=lambda r: r["logloss"])
    return {"best": results[0], "table": results}


# ──────────────────────────────────────────────────────────────
# Persistencia a BD
# ──────────────────────────────────────────────────────────────

def seed_to_db(league_tier: str, start: date, end: date,
               k: float = None, home_adv: float = None) -> dict:
    """Crawl + walk-forward y persiste el ELO final de cada equipo en la BD."""
    k = k if k is not None else settings.ELO_K_FACTOR_BY_LEAGUE.get(league_tier, settings.ELO_K_FACTOR_DEFAULT)
    home_adv = home_adv if home_adv is not None else settings.ELO_HOME_ADVANTAGE

    games = crawl_results(league_tier, start, end)
    if not games:
        return {"league": league_tier, "games": 0, "teams": 0}

    res = walk_forward(games, k=k, home_adv=home_adv)
    elos = res["elos"]

    db = SessionLocal()
    updated = 0
    try:
        for name, rating in elos.items():
            team = _find_or_create_team(db, name, league_tier)
            team.elo_overall = round(rating, 1)
            team.league = league_tier
            updated += 1
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"seed_to_db error: {e}", exc_info=True)
    finally:
        db.close()

    return {
        "league": league_tier, "games": len(games), "teams": updated,
        "accuracy": round(res["accuracy"], 4), "brier": round(res["brier"], 4),
        "logloss": round(res["logloss"], 4), "k": k, "home_adv": home_adv,
    }
