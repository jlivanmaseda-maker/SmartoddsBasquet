"""Recalcula en los picks de linea (sharp-v3) la mediana y el numero de blandas A LA LINEA
APOSTADA, reconstruidas desde odds_history (ultimo snapshot de cada casa antes de crear el
pick). Hasta el 20-oct-2026 se guardaba la mediana a la linea de Pinnacle, que no es
comparable con la cuota cogida (aviso de cordura del vigilante en el pick #298).

Dry-run por defecto; --apply escribe. Uso (VPS):
  cd /opt/SmartOddsBasketball/backend
  venv/bin/python ../scripts/backfill_median_lineas.py [--apply]
"""
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.database import SessionLocal  # noqa: E402
from app.models.bet import Pick  # noqa: E402
from app.models.odds import OddsHistory  # noqa: E402
from app.services import line_markets as lm  # noqa: E402
from app.version import RULE_VERSION_LINES  # noqa: E402


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        picks = db.query(Pick).filter(Pick.rule_version == RULE_VERSION_LINES).all()
        print(f"Picks de linea: {len(picks)}")
        cambios = 0
        for p in picks:
            parsed = lm.lado_y_linea(p.bet_type)
            if not parsed or p.line_value is None:
                continue
            mercado, lado, linea = parsed
            rows = (db.query(OddsHistory).filter(OddsHistory.match_id == p.match_id,
                                                 OddsHistory.recorded_at <= p.created_at)
                    .order_by(OddsHistory.recorded_at).all())
            ultimo = {}
            for h in rows:
                ultimo[h.bookmaker] = h
            precios = []
            for bk, h in ultimo.items():
                if bk in lm.EXCLUDED_SOFT:
                    continue
                if mercado == "spread":
                    linea_home = linea if lado == "home" else -linea
                    if h.spread_line is None or abs(h.spread_line - linea_home) > 1e-9:
                        continue
                    cuota = h.odds_spread_home if lado == "home" else h.odds_spread_away
                else:
                    if h.total_line is None or abs(h.total_line - linea) > 1e-9:
                        continue
                    cuota = h.odds_over if lado == "over" else h.odds_under
                if cuota and cuota > 1.0:
                    precios.append(cuota)
            if not precios:
                print(f"  #{p.id} {p.bet_type}: sin blandas a esa linea en odds_history (se deja como esta)")
                continue
            nueva, n = round(float(statistics.median(precios)), 4), len(precios)
            print(f"  #{p.id} {p.bet_type} cogida {p.best_odds}: mediana {p.median_soft_odds} (n={p.n_soft_books}) "
                  f"-> {nueva} (n={n})")
            if nueva != p.median_soft_odds or n != p.n_soft_books:
                p.median_soft_odds, p.n_soft_books = nueva, n
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
