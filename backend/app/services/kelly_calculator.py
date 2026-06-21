"""Kelly Criterion para el sizing de stake. Identico a tenis/futbol.

f* = (b*p - q) / b   con  b = odds-1, p = prob estimada, q = 1-p
stake = f* * KELLY_FRACTION * bankroll, con topes de WinnerOdds:
  - min_profit_pct, max_profit_pct, max_stake_pct (ver config.py)
"""
from app.config import settings


def kelly_fraction(prob: float, odds: float) -> float:
    """Fraccion optima de Kelly (sin escalar)."""
    if odds <= 1.0 or not (0.0 < prob < 1.0):
        return 0.0
    b = odds - 1.0
    q = 1.0 - prob
    f = (b * prob - q) / b
    return max(0.0, f)


def stake_for(prob: float, odds: float, bankroll: float,
              fraction: float = None) -> float:
    """Stake en divisa aplicando fraccion de Kelly + topes de config."""
    frac = settings.KELLY_FRACTION if fraction is None else fraction
    f = kelly_fraction(prob, odds) * frac
    stake = f * bankroll
    # Tope de stake maximo
    stake = min(stake, settings.KELLY_MAX_STAKE_PCT * bankroll)
    return round(stake, 2)
