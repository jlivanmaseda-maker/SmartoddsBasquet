"""Diagnostico: edge vs Pinnacle SOLO vs edge vs composite sharp, y movimiento
de la linea Pinnacle entre el pick y el cierre.

Pregunta que responde (5-Sep-2026): el CLV medio de los picks es negativo
aunque el edge medio al crearlos era +6%. Si la composite sharp (pinnacle +
betonline + lowvig + 1xbet) esta inflada por casas que no son realmente
sharp en WNBA, los picks con edge SOLO contra Pinnacle deberian rendir mejor.

Uso (en el VPS, solo lectura):
  cd /opt/SmartOddsBasketball/backend
  venv/bin/python ../scripts/analyze_sharp_vs_pinnacle.py
"""
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.database import SessionLocal
from app.models.bet import Pick
from app.models.match import Match
from app.models.odds import OddsHistory
from app.services.clv_calculator import _devig_prob, _side_fields, find_closing_line

SHARPS = ["pinnacle", "betonlineag", "lowvig", "onexbet"]


def snapshot_at(db, match_id, bk, at):
    return (
        db.query(OddsHistory)
        .filter(OddsHistory.match_id == match_id, OddsHistory.bookmaker == bk,
                OddsHistory.recorded_at <= at,
                OddsHistory.odds_home.isnot(None), OddsHistory.odds_away.isnot(None))
        .order_by(OddsHistory.recorded_at.desc())
        .first()
    )


def fair_at(db, match_id, bk, at, bet_type):
    row = snapshot_at(db, match_id, bk, at)
    if not row:
        return None
    this_f, other_f = _side_fields(bet_type)
    p = _devig_prob(getattr(row, this_f), getattr(row, other_f))
    return (1.0 / p) if p else None


def agg(rows):
    n = len(rows)
    if not n:
        return "n=0"
    profit = sum(r["profit"] for r in rows)
    won = sum(1 for r in rows if r["won"])
    clvs = [r["clv"] for r in rows if r["clv"] is not None]
    clv = sum(clvs) / len(clvs) if clvs else float("nan")
    pos = sum(1 for c in clvs if c > 0) / len(clvs) * 100 if clvs else float("nan")
    return (f"n={n:<4} profit={profit:+7.2f}u roi={profit / n * 100:+6.1f}% "
            f"wr={won / n * 100:5.1f}% clv={clv:+5.2f}% clv>0={pos:3.0f}%")


def main():
    db = SessionLocal()
    try:
        picks = db.query(Pick).filter(Pick.result.in_(["won", "lost"])).all()
        matches = {m.id: m for m in db.query(Match).filter(
            Match.id.in_({p.match_id for p in picks})).all()}

        rows = []
        bias = defaultdict(list)   # bk -> [fair_bk / fair_pinn - 1] al crear el pick
        for p in picks:
            m = matches.get(p.match_id)
            if not m or not _side_fields(p.bet_type):
                continue
            fair_pinn_open = fair_at(db, m.id, "pinnacle", p.created_at, p.bet_type)
            close = find_closing_line(db, m, p.bet_type)
            fair_close = close["fair_odds"] if close else None
            for bk in SHARPS[1:]:
                f = fair_at(db, m.id, bk, p.created_at, p.bet_type)
                if f and fair_pinn_open:
                    bias[bk].append((f / fair_pinn_open - 1) * 100)
            rows.append({
                "league": (m.league_tier or "?"),
                "edge_pinn": ((p.best_odds / fair_pinn_open - 1) * 100) if fair_pinn_open else None,
                "edge_comp": p.edge,
                "move": ((fair_close / fair_pinn_open - 1) * 100) if (fair_close and fair_pinn_open) else None,
                "clv": ((p.best_odds / fair_close - 1) * 100) if fair_close else None,
                "profit": p.profit_units or 0.0,
                "won": p.result == "won",
                "odds": p.best_odds,
            })

        print(f"Picks analizados: {len(rows)}  "
              f"(sin Pinnacle al crear: {sum(1 for r in rows if r['edge_pinn'] is None)})")

        for league in sorted({r["league"] for r in rows}):
            rs = [r for r in rows if r["league"] == league]
            print(f"\n=== {league.upper()} ===")
            print("Por EDGE vs PINNACLE solo (al crear el pick):")
            for lo, hi, lab in [(-99, 0, "<0"), (0, 3, "0-3"), (3, 5, "3-5"), (5, 8, "5-8"), (8, 99, "8+")]:
                b = [r for r in rs if r["edge_pinn"] is not None and lo <= r["edge_pinn"] < hi]
                print(f"  {lab:>4}: {agg(b)}")
            print("Sin Pinnacle al crear:", agg([r for r in rs if r["edge_pinn"] is None]))
            moves = [r["move"] for r in rs if r["move"] is not None]
            if moves:
                print(f"Movimiento Pinnacle pick->cierre (fair de NUESTRO lado): "
                      f"media {sum(moves) / len(moves):+.2f}%  "
                      f"(>0 = se alargo = en contra) en {sum(1 for x in moves if x > 0)}/{len(moves)}")
            print("Por EDGE composite (el actual):")
            for lo, hi, lab in [(3, 5, "3-5"), (5, 8, "5-8"), (8, 12, "8-12"), (12, 99, "12+")]:
                b = [r for r in rs if r["edge_comp"] is not None and lo <= r["edge_comp"] < hi]
                print(f"  {lab:>4}: {agg(b)}")

        print("\n=== Sesgo de cada sharp vs Pinnacle al crear el pick (fair_bk/fair_pinn - 1, lado del pick) ===")
        for bk, vals in bias.items():
            print(f"  {bk:>12}: n={len(vals):<4} media {sum(vals) / len(vals):+.2f}%  "
                  f"mas corta que Pinnacle en {sum(1 for v in vals if v < 0) / len(vals) * 100:.0f}% de los picks")
    finally:
        db.close()


if __name__ == "__main__":
    main()
