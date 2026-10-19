"""Simulacion de sharp-v3 sobre odds_history (solo lectura): cuantos picks de handicap y total
habrian salido, por liga y dia, reproduciendo la regla cada 15 minutos con el ultimo snapshot
de cada casa en ese instante (ventana de 24 h, Pinnacle presente, primer instante con valor).

Uso (contra una COPIA de la BD, nunca la de produccion):
  DATABASE_URL=sqlite:////root/tmp_basquet_test/sim.db venv/bin/python ../scripts/simular_sharpv3.py [--desde 2026-10-19]
"""
import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.config import settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.models.odds import OddsHistory  # noqa: E402
from app.services import line_markets as lm  # noqa: E402


def main(desde: str) -> None:
    db = SessionLocal()
    try:
        t0 = datetime.fromisoformat(desde)
        matches = db.query(Match).filter(Match.commence_time >= t0).all()
        print(f"partidos desde {desde}: {len(matches)}")
        picks = []
        for m in matches:
            hist = (db.query(OddsHistory).filter(OddsHistory.match_id == m.id)
                    .order_by(OddsHistory.recorded_at).all())
            if not hist:
                continue
            ct = m.commence_time
            t = max(hist[0].recorded_at, ct - timedelta(hours=settings.PICK_MAX_HOURS_AHEAD))
            hechos = set()
            i = 0
            ultimo = {}
            while t < ct and len(hechos) < 2:
                while i < len(hist) and hist[i].recorded_at <= t:
                    h = hist[i]
                    ultimo[h.bookmaker] = {"spread_line": h.spread_line, "odds_spread_home": h.odds_spread_home,
                                          "odds_spread_away": h.odds_spread_away, "total_line": h.total_line,
                                          "odds_over": h.odds_over, "odds_under": h.odds_under}
                    i += 1
                anchor = ultimo.get(settings.PICK_ANCHOR_BOOKMAKER)
                if anchor:
                    for mercado, lados in (("spread", ("home", "away")), ("total", ("over", "under"))):
                        if mercado in hechos:
                            continue
                        ref = lm.referencia(ultimo, mercado, m.league_tier or "")
                        if not ref:
                            continue
                        best = None
                        for lado in lados:
                            ev = lm.evaluar_lado(ultimo, mercado, lado, ref)
                            if ev and (best is None or ev["priority"] > best["priority"]):
                                best = ev
                        if best:
                            hechos.add(mercado)
                            picks.append((m.league_tier, ct.date().isoformat(), mercado, best["bet_type"], best["bk"],
                                          best["cuota"], round(best["edge"], 1), best["ref_linea"],
                                          round((ct - t).total_seconds() / 3600, 1)))
                t += timedelta(minutes=15)
        por = defaultdict(int)
        for p in picks:
            por[(p[0], p[1], p[2])] += 1
        print("\npicks simulados por liga, dia y mercado:")
        for k in sorted(por):
            print("  ", k, por[k])
        print(f"\ntotal {len(picks)} picks en {len({p[1] for p in picks})} dias")
        if picks:
            edges = sorted(p[6] for p in picks)
            print("edge mediana", edges[len(edges) // 2], "| antelacion mediana h", sorted(p[8] for p in picks)[len(picks) // 2])
            print("ejemplos:")
            for p in picks[:12]:
                print("  ", p)
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2026-10-19T16:00:00")
    main(ap.parse_args().desde)
