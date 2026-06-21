"""BookDif Calculator (agnóstico al deporte — misma lógica que tenis/futbol).

BookDif = (best_soft_odds - sharp_composite) / sharp_composite * 100

Si una soft ofrece 2.10 y Pinnacle ofrece 1.95:
  BookDif = (2.10 - 1.95) / 1.95 * 100 = 7.7%

BookDif > 0 = la soft ofrece MÁS que la sharp = posible valor.
BookDif < 0 = mercado eficiente.
"""
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger("smartodds_basketball.bookdif")

SHARP_BOOKS = set(settings.SHARP_BOOKMAKERS)
SHARP_FALLBACK = set(getattr(settings, "SHARP_FALLBACK_BOOKMAKERS", ["bet365", "fonbet", "bwin"]))
SOFT_BOOKS = set(settings.SOFT_BOOKMAKERS)
EXCHANGE_BOOKS = {"betfair_ex_eu", "betfair_ex_uk", "matchbook", "smarkets"}


def get_sharp_composite(odds_by_bookmaker: dict, field: str) -> Optional[float]:
    """Odds sharp compuestas. Prioridad: Pinnacle -> fallback sharps -> None."""
    sharp_odds = []
    for bk, odds_data in odds_by_bookmaker.items():
        if bk in SHARP_BOOKS:
            val = odds_data.get(field)
            if val and val > 1.0:
                sharp_odds.append(val)
    if sharp_odds:
        return sum(sharp_odds) / len(sharp_odds)

    fallback_odds = []
    for bk, odds_data in odds_by_bookmaker.items():
        if bk in SHARP_FALLBACK:
            val = odds_data.get(field)
            if val and val > 1.0:
                fallback_odds.append(val)
    if fallback_odds:
        return sum(fallback_odds) / len(fallback_odds)

    return None


def get_best_soft_odds(odds_by_bookmaker: dict, field: str) -> Optional[tuple]:
    """Mejor cuota entre casas soft. Returns (odds, bookmaker)."""
    best = None
    best_bk = None
    for bk, odds_data in odds_by_bookmaker.items():
        if bk in EXCHANGE_BOOKS:
            continue
        if bk in SOFT_BOOKS or bk not in SHARP_BOOKS:
            val = odds_data.get(field)
            if val and val > 1.0 and (best is None or val > best):
                best = val
                best_bk = bk
    if best is None:
        return None
    return (best, best_bk)


def calculate_bookdif(odds_by_bookmaker: dict, field: str) -> Optional[float]:
    """BookDif para un mercado específico."""
    sharp = get_sharp_composite(odds_by_bookmaker, field)
    soft = get_best_soft_odds(odds_by_bookmaker, field)
    if sharp is None or soft is None:
        return None
    best_soft_odds, _ = soft
    return round((best_soft_odds - sharp) / sharp * 100, 2)
