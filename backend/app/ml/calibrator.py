"""Calibracion de probabilidades por liga (Platt scaling).

ESQUELETO. Portar de tenis (ml/calibrator.py). Ajusta una regresion logistica
sobre (prob_modelo -> resultado real) por liga para corregir sesgos.
"""


class Calibrator:
    def fit(self, probs, outcomes) -> None:
        """Ajusta Platt scaling. TODO."""
        raise NotImplementedError

    def calibrate(self, prob: float) -> float:
        """Devuelve la probabilidad calibrada. TODO (identidad por ahora)."""
        return prob
