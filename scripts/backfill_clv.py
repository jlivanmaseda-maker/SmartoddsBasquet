"""Backfill de CLV para picks ya resueltos (clv_pct IS NULL).

Contexto (5-Sep-2026): clv_calculator era un esqueleto y ningun pick tenia
CLV. Desde ahora score_resolver lo calcula al liquidar; este script rellena
los historicos usando `odds_history` (ultimo snapshot sharp pre-tipoff).

Uso (en el VPS):
  cd /opt/SmartOddsBasketball/backend
  venv/bin/python ../scripts/backfill_clv.py           # dry-run (resumen)
  venv/bin/python ../scripts/backfill_clv.py --apply   # escribe en DB
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.database import SessionLocal
from app.models.bet import Pick
from app.models.match import Match
from app.services.clv_calculator import compute_pick_clv


def main():
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        picks = db.query(Pick).filter(
            Pick.result.in_(["won", "lost"]),
            Pick.clv_pct.is_(None),
        ).order_by(Pick.id).all()
        print(f"Picks resueltos sin CLV: {len(picks)}")

        ok, miss, by_league = 0, [], {}
        for p in picks:
            m = db.get(Match, p.match_id)
            if compute_pick_clv(db, p, m):
                ok += 1
                lt = (m.league_tier if m else None) or "?"
                by_league.setdefault(lt, []).append(p.clv_pct)
            else:
                miss.append(p.id)

        print(f"Calculados: {ok}   Sin cierre sharp: {len(miss)}")
        if miss:
            print(f"  ids sin cierre: {miss[:30]}{' ...' if len(miss) > 30 else ''}")
        for lt, vals in sorted(by_league.items()):
            avg = sum(vals) / len(vals)
            pos = sum(1 for v in vals if v > 0) / len(vals) * 100
            print(f"  {lt:>8}: n={len(vals):<4} CLV medio={avg:+.2f}%  CLV>0: {pos:.0f}%")

        if apply:
            db.commit()
            print("\nCommit hecho.")
        else:
            db.rollback()
            print("\nDRY-RUN: nada escrito. Ejecutar con --apply para aplicar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
