"""Closing Line Value (CLV) — metrica de calidad de los picks.

CLV = (odds_apostada / closing_odds - 1) * 100
El closing_odds es la cuota sharp (Pinnacle) al cierre del partido.
ESQUELETO. Portar de tenis (services/clv_calculator.py).
"""


def clv_pct(placed_odds: float, closing_odds: float) -> float:
    """CLV en %. Positivo = se cogio mejor cuota que el cierre sharp."""
    if not closing_odds or closing_odds <= 1.0:
        return 0.0
    return (placed_odds / closing_odds - 1.0) * 100.0
