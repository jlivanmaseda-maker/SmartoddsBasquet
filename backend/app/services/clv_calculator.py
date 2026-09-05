"""Closing Line Value (CLV) — metrica de calidad de los picks.

CLV = (odds_apostada / closing_fair_odds - 1) * 100

`closing_fair_odds` es la cuota SHARP al cierre (ultimo snapshot de
OddsHistory ANTES del tipoff) con el margen quitado (devig proporcional, el
mismo que usa value_calculator). Se compara contra la linea sin margen porque
es el test honesto de edge: una cuota igual a la de Pinnacle al cierre ya
tiene ~2-3% de CLV "gratis" si no se quita el vig.

Prioridad de casas para el cierre: pinnacle > betonlineag > lowvig > onexbet
(mismo set que SHARP_BOOKMAKERS). `pinnacle_closing_odds` guarda la cuota
CRUDA de Pinnacle (solo si fue Pinnacle la referencia).

NOTA: la tabla `odds` (upsert) sigue recibiendo cuotas en vivo tras el tipoff,
asi que NO sirve como cierre; hay que ir a `odds_history` filtrando por
recorded_at <= commence_time.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.bet import Pick
from app.models.match import Match
from app.models.odds import OddsHistory

logger = logging.getLogger("smartodds_basketball.clv")

# Orden de preferencia para la cuota de cierre.
CLOSING_BOOKMAKERS = [
    bk for bk in ["pinnacle", "betonlineag", "lowvig", "onexbet"]
    if bk in set(settings.SHARP_BOOKMAKERS)
] or list(settings.SHARP_BOOKMAKERS)


def clv_pct(placed_odds: float, closing_odds: float) -> Optional[float]:
    """CLV en %. Positivo = se cogio mejor cuota que el cierre sharp."""
    if not placed_odds or not closing_odds or closing_odds <= 1.0:
        return None
    return round((placed_odds / closing_odds - 1.0) * 100.0, 2)


def _devig_prob(this_odds, other_odds) -> Optional[float]:
    """Metodo proporcional (igual que value_calculator._devig_prob)."""
    if not this_odds or not other_odds or this_odds <= 1.0 or other_odds <= 1.0:
        return None
    imp_this = 1.0 / this_odds
    imp_other = 1.0 / other_odds
    total = imp_this + imp_other
    return imp_this / total if total > 0 else None


def _side_fields(bet_type: str):
    """('odds_home','odds_away') para el lado apostado, o None si no es ML."""
    if bet_type == "match_winner_home":
        return "odds_home", "odds_away"
    if bet_type == "match_winner_away":
        return "odds_away", "odds_home"
    return None


def _naive_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def find_closing_line(db: Session, match: Match, bet_type: str) -> Optional[dict]:
    """Ultimo snapshot sharp pre-tipoff para el lado del pick.

    Returns: {"bookmaker", "raw_odds", "fair_odds", "recorded_at"} o None.
    """
    fields = _side_fields(bet_type)
    if not fields or not match.commence_time:
        return None
    this_f, other_f = fields
    cutoff = _naive_utc(match.commence_time)

    for bk in CLOSING_BOOKMAKERS:
        row = (
            db.query(OddsHistory)
            .filter(
                OddsHistory.match_id == match.id,
                OddsHistory.bookmaker == bk,
                OddsHistory.recorded_at <= cutoff,
                OddsHistory.odds_home.isnot(None),
                OddsHistory.odds_away.isnot(None),
            )
            .order_by(OddsHistory.recorded_at.desc())
            .first()
        )
        if not row:
            continue
        raw = getattr(row, this_f)
        prob = _devig_prob(raw, getattr(row, other_f))
        if not prob:
            continue
        return {
            "bookmaker": bk,
            "raw_odds": raw,
            "fair_odds": round(1.0 / prob, 4),
            "recorded_at": row.recorded_at,
        }
    return None


def compute_pick_clv(db: Session, pick: Pick, match: Optional[Match] = None) -> bool:
    """Rellena closing_odds / closing_bookmaker / pinnacle_closing_odds / clv_pct.

    No hace commit. Returns True si se pudo calcular.
    """
    match = match or db.get(Match, pick.match_id)
    if not match or not pick.best_odds:
        return False
    closing = find_closing_line(db, match, pick.bet_type)
    if not closing:
        return False

    pick.closing_odds = closing["fair_odds"]
    pick.closing_bookmaker = closing["bookmaker"]
    pick.pinnacle_closing_odds = (
        closing["raw_odds"] if closing["bookmaker"] == "pinnacle" else None
    )
    pick.clv_pct = clv_pct(pick.best_odds, closing["fair_odds"])
    return pick.clv_pct is not None


def compute_match_clv(db: Session, match: Match) -> int:
    """CLV para todos los picks del partido que aun no lo tengan. Returns n."""
    picks = db.query(Pick).filter(
        Pick.match_id == match.id,
        Pick.clv_pct.is_(None),
    ).all()
    done = 0
    for p in picks:
        try:
            if compute_pick_clv(db, p, match):
                done += 1
        except Exception as e:  # nunca romper la liquidacion por el CLV
            logger.warning(f"CLV pick #{p.id}: {e}")
    return done
