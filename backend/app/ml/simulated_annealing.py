"""Optimizacion de pesos del ensemble via Simulated Annealing.

ESQUELETO. Portar de tenis (ml/simulated_annealing.py). Corre semanalmente
(lunes) sobre el backtest historico para re-optimizar los pesos de los
componentes maximizando edge * hit_rate (SA_OBJECTIVE). Parametros en config.
"""
from app.config import settings


def optimize_weights(picks) -> dict:
    """Devuelve el dict de pesos optimizados. TODO."""
    if len(picks) < settings.SA_MIN_PICKS:
        return {}
    raise NotImplementedError("Portar de SmartoddsTenis/ml/simulated_annealing.py")
