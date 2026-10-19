"""Rellena en los picks viejos la mediana de las blandas y Pinnacle en el instante
del pick, reconstruidas desde odds_history (19-oct-2026).

Para cada pick sin median_soft_odds: ultimo snapshot de cada casa con
recorded_at <= created_at; mediana de las blandas (sin sharps ni exchanges) y
Pinnacle (cruda y sin margen) del lado apostado. Es la misma definicion que
usa value_calculator para los picks nuevos.

Dry-run por defecto; --apply escribe. Uso (VPS):
  cd /opt/SmartOddsBasketball/backend
  venv/bin/python ../scripts/backfill_median.py [--apply]
"""
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.config import settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.bet import Pick  # noqa: E402
from app.models.odds import OddsHistory  # noqa: E402
from app.services.clv_calculator import _devig_prob, _side_fields  # noqa: E402

SHARP = set(settings.SHARP_BOOKMAKERS)
EXCH = {"betfair_ex_eu", "betfair_ex_uk", "betfair_ex_au", "matchbook", "smarkets"}
ANCHOR = settings.PICK_ANCHOR_BOOKMAKER


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        picks = db.query(Pick).filter(Pick.median_soft_odds.is_(None)).all()
        print(f"Picks sin mediana: {len(picks)}")
        if not picks:
            return 0
        mids = sorted({p.match_id for p in picks})
        hist = defaultdict(list)
        rows = (db.query(OddsHistory.match_id, OddsHistory.bookmaker, OddsHistory.odds_home,
                         OddsHistory.odds_away, OddsHistory.recorded_at)
                .filter(OddsHistory.match_id.in_(mids))
                .order_by(OddsHistory.recorded_at).all())
        for mid, bk, oh, oa, rec in rows:
            hist[mid].append((rec, bk, oh, oa))
        hechos = sin_datos = 0
        for p in picks:
            fields = _side_fields(p.bet_type)
            if not fields or not p.created_at:
                sin_datos += 1
                continue
            last = {}
            for rec, bk, oh, oa in hist.get(p.match_id, []):
                if rec > p.created_at:
                    break
                last[bk] = (oh, oa)
            soft = []
            for bk, (oh, oa) in last.items():
                if bk in SHARP or bk in EXCH:
                    continue
                v = oh if fields[0] == "odds_home" else oa
                if v and v > 1.0:
                    soft.append(v)
            if not soft:
                sin_datos += 1
                continue
            p.median_soft_odds = round(float(statistics.median(soft)), 4)
            p.n_soft_books = len(soft)
            pin = last.get(ANCHOR)
            if pin:
                raw = pin[0] if fields[0] == "odds_home" else pin[1]
                prob = _devig_prob(pin[0], pin[1]) if fields[0] == "odds_home" else _devig_prob(pin[1], pin[0])
                if raw and raw > 1.0:
                    p.pinnacle_odds_at_pick = raw
                if prob:
                    p.pinnacle_fair_at_pick = round(1.0 / prob, 4)
            hechos += 1
        print(f"Con mediana reconstruida: {hechos}; sin snapshots previos: {sin_datos}")
        if apply and hechos:
            db.commit()
            print("APLICADO")
        else:
            db.rollback()
            print("dry-run: nada escrito" if not apply else "nada que escribir")
        return hechos
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
