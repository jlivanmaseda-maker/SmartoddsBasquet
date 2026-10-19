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
ODDS_BUCKETS = [(1.0, 1.6), (1.6, 2.0), (2.0, 3.0), (3.0, 99.0)]

HEADER = f"{'n':>5} {'profit':>9} {'roi%':>8} {'winrate%':>9} {'clv%':>7} {'clv>0':>6}"


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


def _clv(picks):
    """(clv medio %, % picks con clv>0) o ('-', '-') si no hay CLV."""
    vals = [p.clv_pct for p in picks if p.clv_pct is not None]
    if not vals:
        return ("-", "-")
    avg = sum(vals) / len(vals)
    pos = sum(1 for v in vals if v > 0) / len(vals) * 100
    return (f"{avg:+.1f}", f"{pos:.0f}%")


def _row(label, picks):
    n, profit, roi, wr = _roi(picks)
    clv, pos = _clv(picks)
    return f"{label:<12} {n:>5} {profit:>9.2f} {roi:>8.1f} {wr:>9.1f} {clv:>7} {pos:>6}"


def _roi_se(picks, odds_attr):
    """ROI (%) +- 2 errores estandar a la cuota `odds_attr`, solo won/lost con esa cuota.

    Devuelve (n, roi, 2se) o (0, None, None). 1 unidad por pick.
    """
    vals = []
    for p in picks:
        if p.result not in ("won", "lost"):
            continue
        o = getattr(p, odds_attr, None)
        if not o or o <= 1.0:
            continue
        vals.append((o - 1.0) if p.result == "won" else -1.0)
    n = len(vals)
    if n == 0:
        return (0, None, None)
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / n
    se = (var ** 0.5) / (n ** 0.5)
    return (n, m * 100, 2 * se * 100)


def _fmt_roi(t):
    n, roi, e2 = t
    return "   n=0    " if not n else f"{roi:+6.1f}%+-{e2:4.1f} (n={n})"


def _regla_row(label, picks):
    """Una regla: ROI a cuota cogida, a mediana de blandas y al cierre justo de Pinnacle."""
    clv, pos = _clv(picks)
    return (f"{label:<22} cogida {_fmt_roi(_roi_se(picks, 'best_odds'))}  "
            f"mediana {_fmt_roi(_roi_se(picks, 'median_soft_odds'))}  "
            f"cierre {_fmt_roi(_roi_se(picks, 'closing_odds'))}  clv {clv}% ({pos} >0)")


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

        matches = {m.id: m for m in db.query(Match).filter(
            Match.id.in_({p.match_id for p in picks})).all()}
        n_clv = sum(1 for p in picks if p.clv_pct is not None)
        print(f"Con CLV (vs cierre sharp sin margen): {n_clv}")

        print("\n=== Por bucket de EDGE ===")
        print(f"{'edge':<12} {HEADER}")
        for lo, hi in EDGE_BUCKETS:
            bucket = [p for p in picks if lo <= (p.edge or 0) < hi]
            print(_row(f"{lo}-{hi}", bucket))

        print("\n=== Por bucket de CUOTA ===")
        print(f"{'cuota':<12} {HEADER}")
        for lo, hi in ODDS_BUCKETS:
            bucket = [p for p in picks if lo <= (p.best_odds or 0) < hi]
            print(_row(f"{lo}-{hi}", bucket))

        print("\n=== Por LIGA ===")
        by_league = {}
        for p in picks:
            m = matches.get(p.match_id)
            lt = (m.league_tier if m else None) or "?"
            by_league.setdefault(lt, []).append(p)
        print(f"{'liga':<12} {HEADER}")
        for lt, ps in sorted(by_league.items()):
            print(_row(lt, ps))

        print("\n=== Por LIGA y MES ===")
        by_lm = {}
        for p in picks:
            m = matches.get(p.match_id)
            lt = (m.league_tier if m else None) or "?"
            mes = p.created_at.strftime("%Y-%m") if p.created_at else "?"
            by_lm.setdefault((lt, mes), []).append(p)
        print(f"{'liga/mes':<12} {HEADER}")
        for (lt, mes), ps in sorted(by_lm.items()):
            print(_row(f"{lt[:4]} {mes}", ps))

        print("\n=== Por REGLA (cada una desde su despliegue; ROI +- 2 errores estandar) ===")
        by_rule = {}
        for p in picks:
            by_rule.setdefault(p.rule_version or "?", []).append(p)
        for rv, ps in sorted(by_rule.items()):
            first = min((p.created_at for p in ps if p.created_at), default=None)
            desde = first.strftime("%d-%b") if first else "?"
            print(_regla_row(f"{rv} (desde {desde})", ps))
            # sharp-v3: separar handicap y total, con los puntos de linea frente al cierre
            por_mercado = {}
            for p in ps:
                m = "handicap" if p.bet_type.startswith("spread_") else \
                    "total" if p.bet_type.startswith("total_points_") else "ganador"
                por_mercado.setdefault(m, []).append(p)
            if len(por_mercado) > 1:
                for m, pm in sorted(por_mercado.items()):
                    lc = [p.line_clv for p in pm if getattr(p, "line_clv", None) is not None]
                    extra = f"  linea vs cierre {sum(lc) / len(lc):+.2f} pts (n={len(lc)})" if lc else ""
                    print(_regla_row(f"   {m}", pm) + extra)
        print("  Lectura TT: publicar solo con >= 300 picks y ROI a mediana - 2 errores > 0.")

        print("\n=== SHADOW vs ACTIVE ===")
        for label, flag in (("shadow", True), ("active", False)):
            ps = [p for p in picks if bool(p.is_shadow) == flag]
            n, profit, roi, wr = _roi(ps)
            clv, pos = _clv(ps)
            print(f"  {label:>7}: n={n} profit={profit:.2f}u roi={roi:.1f}% "
                  f"winrate={wr:.1f}% clv={clv}% clv>0={pos}")
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
