"""Recalcula el CLV (clv_pct, closing_odds, closing_line, line_clv) de los picks de linea
(sharp-v3) ya liquidados con el clv_calculator vigente. 21-oct-2026: el CLV en % de los
picks de visitante salia invertido (se pasaba la linea del visitante donde se esperaba la
del local); los puntos de linea (line_clv) eran correctos.

Dry-run por defecto; --apply escribe. Uso (VPS):
  cd /opt/SmartOddsBasketball/backend
  venv/bin/python ../scripts/recalcular_clv_lineas.py [--apply]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.database import SessionLocal  # noqa: E402
from app.models.bet import Pick  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.services.clv_calculator import compute_pick_clv  # noqa: E402
from app.version import RULE_VERSION_LINES  # noqa: E402


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        picks = db.query(Pick).filter(Pick.rule_version == RULE_VERSION_LINES, Pick.result.isnot(None)).all()
        print(f"Picks de linea liquidados: {len(picks)}")
        cambios = 0
        for p in picks:
            antes = (p.clv_pct, p.closing_odds, p.closing_line, p.line_clv)
            m = db.get(Match, p.match_id)
            ok = compute_pick_clv(db, p, m)
            despues = (p.clv_pct, p.closing_odds, p.closing_line, p.line_clv)
            print(f"  #{p.id} {p.bet_type} cogida {p.best_odds}: clv {antes[0]} -> {despues[0]} "
                  f"(cierre justo {antes[1]} -> {despues[1]}, linea {antes[3]} -> {despues[3]}){'' if ok else '  SIN CIERRE'}")
            if ok and antes != despues:
                cambios += 1
        if apply and cambios:
            db.commit()
            print(f"APLICADO: {cambios} picks")
        else:
            db.rollback()
            print(f"dry-run: {cambios} picks cambiarian" if not apply else "nada que cambiar")
        return cambios
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
