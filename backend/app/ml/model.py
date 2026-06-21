"""Ensemble de prediccion para basket.

Adaptado del ensemble de tenis (5 componentes) al deporte de equipo. Cada
componente devuelve P(gana el local) en [0,1]; el ensemble pondera con los
pesos de config.py y renormaliza por los componentes con datos disponibles
(igual filosofia que tenis: si un componente no aporta, se reparte su peso).

Componentes:
  1. ELO Team        — ELO global + ventaja de cancha (ELO_HOME_ADVANTAGE)
  2. Net Rating      — diferencia de net rating (ORtg-DRtg) local vs visitante
  3. Form            — win rate ultimos 10
  4. Rest/Fatiga     — back-to-back / dias de descanso
  5. Home Court      — sesgo fijo de localia
  + H2H              — (placeholder: requiere historial de enfrentamientos)

NOTA v1: con equipos recien creados (ELO 1500, stats None) el modelo devuelve
~0.5 + ventaja de local. Es deliberado: el sistema arranca en SHADOW y se
calibra cuando hay datos (seed de ELO historico + backtest + SA).
"""
import logging

from app.config import settings

logger = logging.getLogger("smartodds_basketball.model")


def elo_expected(elo_a: float, elo_b: float) -> float:
    """Probabilidad esperada de A segun ELO."""
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def _logistic(x: float, scale: float) -> float:
    """Mapea una diferencia a [0,1] con una logistica suave."""
    import math
    return 1.0 / (1.0 + math.exp(-x / scale))


def _comp_elo(home, away) -> float:
    home_elo = (home.elo_overall or 1500.0) + settings.ELO_HOME_ADVANTAGE
    away_elo = away.elo_overall or 1500.0
    return elo_expected(home_elo, away_elo)


def _comp_net_rating(home, away):
    """Diferencia de Net Rating -> prob. None si falta el dato en algun equipo."""
    if home.net_rating is None or away.net_rating is None:
        return None
    # +3.5 de net rating ~ una victoria esperada clara; scale calibrable.
    diff = (home.net_rating - away.net_rating)
    return _logistic(diff, scale=7.0)


def _comp_form(home, away):
    if home.win_rate_last_10 is None or away.win_rate_last_10 is None:
        return None
    diff = (home.win_rate_last_10 - away.win_rate_last_10)
    return 0.5 + diff * 0.5  # diff en [-1,1] -> prob en [0,1]


def _comp_rest(home, away):
    """Ajuste por descanso/back-to-back. Devuelve prob centrada en 0.5."""
    h_b2b = bool(getattr(home, "_b2b", False))
    a_b2b = bool(getattr(away, "_b2b", False))
    if not h_b2b and not a_b2b:
        return None
    adj = 0.0
    if a_b2b:
        adj += 0.04   # visitante cansado favorece al local
    if h_b2b:
        adj -= 0.04
    return min(max(0.5 + adj, 0.02), 0.98)


def _comp_home_court(home, away) -> float:
    """Sesgo fijo de localia (en basket el local gana ~0.60 de media)."""
    return 0.60


def predict_match(home_team, away_team, context: dict = None) -> float:
    """Devuelve P(gana el local) combinando los componentes disponibles.

    context puede traer flags de back-to-back/descanso por equipo.
    """
    context = context or {}
    # Permitir override de back-to-back via context para el componente rest.
    if "home_b2b" in context:
        setattr(home_team, "_b2b", context["home_b2b"])
    if "away_b2b" in context:
        setattr(away_team, "_b2b", context["away_b2b"])

    components = [
        (settings.ELO_TEAM_WEIGHT, _comp_elo(home_team, away_team)),
        (settings.NET_RATING_WEIGHT, _comp_net_rating(home_team, away_team)),
        (settings.FORM_WEIGHT, _comp_form(home_team, away_team)),
        (settings.REST_WEIGHT, _comp_rest(home_team, away_team)),
        (settings.HOME_COURT_WEIGHT, _comp_home_court(home_team, away_team)),
        # H2H: TODO cuando exista historial de enfrentamientos.
    ]

    total_w = 0.0
    acc = 0.0
    for weight, prob in components:
        if prob is None:
            continue
        acc += weight * prob
        total_w += weight

    if total_w == 0.0:
        return 0.5
    p = acc / total_w
    return min(max(p, 0.01), 0.99)
