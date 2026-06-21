"""Sistema ELO para equipos de basket.

Adaptado de tenis: en vez de ELO por superficie, ELO global + ELO local/
visitante y ventaja de cancha (ELO_HOME_ADVANTAGE). K-factor por liga
(ELO_K_FACTOR_BY_LEAGUE). Opcional: margen de victoria (MOV multiplier),
muy predictivo en basket.
"""
from app.config import settings


def expected_score(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def k_factor(league: str) -> int:
    return settings.ELO_K_FACTOR_BY_LEAGUE.get(league, settings.ELO_K_FACTOR_DEFAULT)


def update_after_game(home_team, away_team, home_won: bool, league: str,
                      margin: int = None) -> None:
    """Actualiza el ELO de ambos equipos tras un partido. TODO completar.

    margin (diferencia de puntos) permite aplicar un multiplicador de margen
    de victoria (MOV), recomendado en basket. Por ahora sin MOV.
    """
    k = k_factor(league)
    home_elo = (home_team.elo_overall or 1500.0) + settings.ELO_HOME_ADVANTAGE
    away_elo = away_team.elo_overall or 1500.0
    exp_home = expected_score(home_elo, away_elo)
    actual_home = 1.0 if home_won else 0.0
    delta = k * (actual_home - exp_home)
    home_team.elo_overall = (home_team.elo_overall or 1500.0) + delta
    away_team.elo_overall = (away_team.elo_overall or 1500.0) - delta
    # TODO: actualizar elo_home / elo_away por separado y games_total.
