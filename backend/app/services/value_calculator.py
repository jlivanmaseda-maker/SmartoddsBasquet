"""Value calculator — genera Picks (moneyline) con el método SHARP.

PORTADO DEL MÉTODO REAL DE TENIS (el que de verdad tiene valor, replica a
BetBurger): la señal primaria NO es el modelo ELO, sino las casas SHARP.

Para cada lado (home/away) de un partido:
  1. SHARP devig: por cada casa sharp (Pinnacle, 1xBet) se quita el margen
     (devig proporcional con el lado contrario) y se promedian -> prob "justa".
     fair_odds = 1 / avg_sharp_prob.
  2. best_soft = mejor cuota entre casas blandas (excluye sharps y exchanges).
  3. edge = (sharp_prob - implied_best_soft) / implied_best_soft * 100
            = cuánto ofrece la blanda por encima de lo que la sharp dice que vale.
  4. Filtro mixed-line: si la sharp es >3x la mediana soft -> línea corrupta, fuera.
  5. BookDif = (best_soft - sharp_composite) / sharp_composite * 100 (señal extra).
  6. Si NO hay sharp -> fallback al modelo ELO (predict_match) y el pick va SHADOW.

El edge se mide contra la sharp devig, NO contra el modelo. El modelo solo entra
cuando no hay datos sharp.
"""
import logging
from datetime import datetime, timezone

import numpy as np

from app.config import settings
from app.db.database import SessionLocal
from app.models.match import Match
from app.models.team import Team
from app.models.odds import Odds
from app.models.bet import Pick, PickModelDetail
from app.ml.model import predict_match
from app.services.bookdif_calculator import calculate_bookdif, get_sharp_composite

logger = logging.getLogger("smartodds_basketball.value")

# Casas sharp para el devig (avg-line) — ESPECÍFICAS DE BASKET, desde config:
# {pinnacle, betonlineag, lowvig, onexbet}. Ver nota en config.SHARP_BOOKMAKERS.
SHARP_BKS = set(settings.SHARP_BOOKMAKERS)
EXCHANGE_BKS = {"betfair_ex_eu", "betfair_ex_uk", "betfair_ex_au", "matchbook", "smarkets"}
EXCLUDED_SOFT = SHARP_BKS | EXCHANGE_BKS


def _odds_by_bk(odds_rows) -> dict:
    """{bookmaker: {'odds_home':x, 'odds_away':y}} a partir de filas Odds."""
    d = {}
    for o in odds_rows:
        d[o.bookmaker] = {"odds_home": o.odds_home, "odds_away": o.odds_away}
    return d


def _devig_prob(this_odds, other_odds):
    """Quita el margen (método proporcional) -> prob real del lado 'this'."""
    if not this_odds or not other_odds or this_odds <= 1.0 or other_odds <= 1.0:
        return None
    imp_this = 1.0 / this_odds
    imp_other = 1.0 / other_odds
    total = imp_this + imp_other
    if total <= 0:
        return None
    return imp_this / total


def _best_soft(odds_by_bk: dict, field: str):
    """Mejor cuota soft (excluye sharps y exchanges). Returns (odds, bk)."""
    best, best_bk = None, None
    for bk, data in odds_by_bk.items():
        if bk in EXCLUDED_SOFT:
            continue
        val = data.get(field)
        if val and val > 1.0 and (best is None or val > best):
            best, best_bk = val, bk
    return best, best_bk


def _evaluate_side(odds_by_bk: dict, field: str, opp_field: str, model_prob: float) -> dict:
    """Evalúa un lado. Devuelve dict con edge/sharp_prob/best_odds/... o None."""
    best_odds, best_bk = _best_soft(odds_by_bk, field)
    if not best_odds or best_odds < settings.SYSTEM_MIN_ODDS or best_odds > settings.SYSTEM_MAX_ODDS:
        return None

    # ---- Sharp devig (avg-line) ----
    sharp_probs = []
    for bk in SHARP_BKS:
        data = odds_by_bk.get(bk, {})
        prob = _devig_prob(data.get(field), data.get(opp_field))
        if prob and 0.01 < prob < 0.99:
            sharp_probs.append(prob)

    fair_odds = None
    if sharp_probs:
        avg_sharp_prob = sum(sharp_probs) / len(sharp_probs)
        fair_odds = 1.0 / avg_sharp_prob
    else:
        # Fallback: cuota cruda de 1xBet o Pinnacle
        raw = odds_by_bk.get("onexbet", {}).get(field) or odds_by_bk.get("pinnacle", {}).get(field)
        if raw and raw > 1.0:
            fair_odds = raw

    # Filtro mixed-line: sharp >3x mediana soft -> línea corrupta
    if fair_odds and fair_odds > 1.0:
        soft_vals = [
            data.get(field) for bk, data in odds_by_bk.items()
            if bk not in EXCLUDED_SOFT and data.get(field) and data.get(field) > 1.0
        ]
        if soft_vals:
            median_soft = float(np.median(soft_vals))
            if median_soft > 0 and fair_odds / median_soft > 3.0:
                return None

    # Probabilidad de referencia: sharp si hay, si no el modelo (fallback)
    has_sharp = bool(fair_odds and fair_odds > 1.0)
    ref_prob = (1.0 / fair_odds) if has_sharp else model_prob

    implied = 1.0 / best_odds
    edge = (ref_prob - implied) / implied * 100.0

    if edge < settings.SYSTEM_MIN_EDGE or edge > settings.SA_MAX_EDGE:
        return None

    bookdif = calculate_bookdif(odds_by_bk, field)
    sharp_avg = get_sharp_composite(odds_by_bk, field)

    # Dispersión: (mejor cuota / mediana soft - 1) * 100
    soft_vals = [
        data.get(field) for bk, data in odds_by_bk.items()
        if bk not in EXCLUDED_SOFT and data.get(field) and data.get(field) > 1.0
    ]
    dispersion = None
    if soft_vals:
        med = float(np.median(soft_vals))
        if med > 0:
            dispersion = round((best_odds / med - 1) * 100, 2)

    return {
        "best_odds": best_odds, "best_bk": best_bk,
        "ref_prob": ref_prob, "edge": edge, "has_sharp": has_sharp,
        "bookdif": bookdif, "sharp_avg": sharp_avg, "dispersion": dispersion,
        "priority": edge * ref_prob,
    }


def generate_picks(db=None) -> int:
    """Recorre partidos próximos y crea picks con valor (método sharp). Nº picks."""
    own = db is None
    if own:
        db = SessionLocal()
    created = 0
    try:
        now = datetime.now(timezone.utc)
        matches = db.query(Match).filter(
            Match.is_completed == False,  # noqa: E712
            Match.is_live == False,       # noqa: E712
        ).all()

        for match in matches:
            ct = match.commence_time
            if ct is None:
                continue
            if ct.tzinfo is None:
                ct = ct.replace(tzinfo=timezone.utc)
            if ct <= now:
                continue

            # Guard de conflicto: ya hay pick activo
            if db.query(Pick).filter(
                Pick.match_id == match.id, Pick.is_active == True  # noqa: E712
            ).first():
                continue

            odds_rows = db.query(Odds).filter(Odds.match_id == match.id).all()
            if not odds_rows:
                continue
            obk = _odds_by_bk(odds_rows)

            # Modelo (fallback) — para lados sin sharp
            home = db.query(Team).filter(Team.id == match.home_team_id).first()
            away = db.query(Team).filter(Team.id == match.away_team_id).first()
            model_home = predict_match(home, away) if (home and away) else 0.5
            match.prob_home = model_home
            match.prob_away = 1.0 - model_home

            sides = [
                ("home", "odds_home", "odds_away", model_home),
                ("away", "odds_away", "odds_home", 1.0 - model_home),
            ]
            best = None
            for side, field, opp, mprob in sides:
                ev = _evaluate_side(obk, field, opp, mprob)
                if ev and (best is None or ev["priority"] > best["priority"]):
                    ev["side"] = side
                    best = ev
            if not best:
                continue

            # Shadow: sin sharp (solo modelo) o liga en fase de calibración
            reasons = []
            if not best["has_sharp"]:
                reasons.append("no_sharp")
            if (match.league_tier or "") in settings.SHADOW_TIERS:
                reasons.append(match.league_tier)
            is_shadow = len(reasons) > 0

            pick = Pick(
                match_id=match.id,
                bet_type=f"match_winner_{best['side']}",
                best_odds=best["best_odds"],
                best_bookmaker=best["best_bk"],
                estimated_probability=best["ref_prob"],
                edge=best["edge"],
                bookdif=best["bookdif"],
                sharp_odds=round(best["sharp_avg"], 4) if best["sharp_avg"] else None,
                dispersion=best["dispersion"],
                priority_score=best["priority"],
                is_active=True,
                is_shadow=is_shadow,
                shadow_reasons=",".join(reasons) or None,
                created_at=now,
            )
            db.add(pick)
            db.flush()
            db.add(PickModelDetail(
                pick_id=pick.id, match_id=match.id,
                ensemble_prob=model_home if best["side"] == "home" else 1.0 - model_home,
            ))
            created += 1
            tag = "SHADOW" if is_shadow else "ACTIVE"
            src = "sharp" if best["has_sharp"] else "model"
            logger.info(
                f"[{tag}/{src}] {pick.bet_type} {match.home_team} vs {match.away_team} "
                f"@ {best['best_odds']} ({best['best_bk']}) edge={best['edge']:.1f}% "
                f"bookdif={best['bookdif']}"
            )
            if not is_shadow:
                try:
                    from app.services import notification_service
                    notification_service.send_new_pick(pick, match)
                except Exception:
                    pass

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"generate_picks error: {e}", exc_info=True)
    finally:
        if own:
            db.close()
    return created
