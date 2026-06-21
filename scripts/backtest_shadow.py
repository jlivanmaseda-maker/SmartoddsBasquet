"""Backtest de picks acumulados en SHADOW — calibra SYSTEM_MIN_EDGE.

A diferencia de ml/elo_seed.py (backtest del MODELO con resultados historicos
de ESPN), este script mide el RENDIMIENTO REAL de los picks que el sistema ha
ido generando: bucketea por edge y por liga y calcula ROI/winrate.

Es el patron "shadow" de tenis/futbol: se deja correr el sistema en shadow unas
semanas, se acumulan picks resueltos (edge + result + profit_units) y entonces
este script dice donde poner el umbral de edge y que ligas pasan a ACTIVE.

Uso (en el VPS):
  cd /opt/SmartOddsBasketball/backend
  ../venv/bin/python ../scripts/backtest_shadow.py
"""
import sys
import os
import io
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.database import SessionLocal
from app.models.bet import Pick
from app.models.match import Match


EDGE_BUCKETS = [(0, 3), (3, 5), (5, 8), (8, 12), (12, 100)]


def _roi(picks):
    n = len(picks)
    if not n:
        return (0, 0.0, 0.0, 0.0)
    staked = n  # 1u por pick
    profit = sum(p.profit_units or 0.0 for p in picks)
    won = sum(1 for p in picks if p.result == "won")
    settled = sum(1 for p in picks if p.result in ("won", "lost"))
    winrate = (won / settled * 100) if settled else 0.0
    roi = (profit / staked * 100) if staked else 0.0
    return (n, profit, roi, winrate)


def main():
    db = SessionLocal()
    try:
        picks = db.query(Pick).filter(
            Pick.result.in_(["won", "lost", "void"])
        ).all()
        print(f"Picks resueltos: {len(picks)}")
        if not picks:
            print("Sin datos todavia — dejar correr el sistema en shadow y reintentar.")
            return

        print("\n=== Por bucket de EDGE ===")
        print(f"{'edge':>10} {'n':>5} {'profit':>9} {'roi%':>8} {'winrate%':>9}")
        for lo, hi in EDGE_BUCKETS:
            bucket = [p for p in picks if lo <= (p.edge or 0) < hi]
            n, profit, roi, wr = _roi(bucket)
            print(f"{lo:>3}-{hi:<6} {n:>5} {profit:>9.2f} {roi:>8.1f} {wr:>9.1f}")

        print("\n=== Por LIGA ===")
        by_league = {}
        for p in picks:
            m = db.query(Match).filter(Match.id == p.match_id).first()
            lt = (m.league_tier if m else None) or "?"
            by_league.setdefault(lt, []).append(p)
        print(f"{'liga':>12} {'n':>5} {'profit':>9} {'roi%':>8} {'winrate%':>9}")
        for lt, ps in sorted(by_league.items()):
            n, profit, roi, wr = _roi(ps)
            print(f"{lt:>12} {n:>5} {profit:>9.2f} {roi:>8.1f} {wr:>9.1f}")

        print("\n=== SHADOW vs ACTIVE ===")
        for label, flag in (("shadow", True), ("active", False)):
            ps = [p for p in picks if bool(p.is_shadow) == flag]
            n, profit, roi, wr = _roi(ps)
            print(f"  {label:>7}: n={n} profit={profit:.2f}u roi={roi:.1f}% winrate={wr:.1f}%")
    finally:
        db.close()


def _n_resolved() -> int:
    db = SessionLocal()
    try:
        return db.query(Pick).filter(Pick.result.in_(["won", "lost", "void"])).count()
    finally:
        db.close()


def run(send_telegram: bool = False):
    """Ejecuta el informe. Si send_telegram y hay datos, lo manda por Telegram."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        main()
    report = buf.getvalue()
    print(report)

    if send_telegram and _n_resolved() > 0:
        try:
            from app.services.notification_service import _send_telegram
            # Texto plano monoespaciado (sin Markdown) para no romper formato.
            _send_telegram("BACKTEST SHADOW — Basket\n\n" + report)
        except Exception as e:
            print(f"[telegram] error: {e}")


if __name__ == "__main__":
    run(send_telegram="--telegram" in sys.argv)
