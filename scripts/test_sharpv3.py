"""Pruebas de sharp-v3 (handicap y total) sobre una BD SQLite temporal. Sin pytest:

  cd backend && python ../scripts/test_sharpv3.py

Comprueba: la normal y el push, la referencia de Pinnacle, que a linea igual con precios
peores NO hay pick y con linea desfasada SI, los bet_type, que generate_picks crea ganador +
handicap + total del mismo partido (guard por mercado), la liquidacion (gana / pierde / push)
y el CLV de linea contra el cierre de Pinnacle. Y la PARIDAD del ganador: el canario del
ganador da exactamente lo mismo que antes de sharp-v3.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_tmp = tempfile.mkdtemp(prefix="basquet_v3_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "test.db").replace("\\", "/")
os.environ["BASKET_LOGS"] = _tmp
os.environ["BASKET_VIGILANTE_ESTADO"] = os.path.join(_tmp, "estado.json")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from app.db.database import SessionLocal, init_db  # noqa: E402
from app.models.bet import Pick  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.models.odds import Odds, OddsHistory  # noqa: E402
from app.services import line_markets as lm  # noqa: E402
from app.services import value_calculator, score_resolver  # noqa: E402
from app.services.odds_fetcher import _find_or_create_team  # noqa: E402
from app.version import RULE_VERSION, RULE_VERSION_LINES  # noqa: E402

import vigilante  # noqa: E402


def cerca(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_normal_y_push():
    assert cerca(lm._phi(0.0), 0.5) and cerca(lm._phi_inv(0.5), 0.0, 1e-9)
    for p in (0.1, 0.3, 0.5, 0.7, 0.9, 0.975):
        assert cerca(lm._phi(lm._phi_inv(p)), p, 1e-8), p
    # media implicada: P(X > 5.5) = 0.5 -> mu = 5.5
    assert cerca(lm.media_implicada(5.5, 0.5, 12.5), 5.5, 1e-9)
    pg, pp = lm.prob_gana_push(5.5, 12.5, 5.5)          # linea -5.5: sin push, P(X >= 6) con mu 5.5
    assert pp == 0.0 and cerca(pg, 0.5, 1e-9)       # P(X > 5.5) con mu 5.5 es exactamente 0,5
    pg2, pp2 = lm.prob_gana_push(5.5, 12.5, 6.0)        # linea -6 (entera): push posible
    assert 0.02 < pp2 < 0.04 and pg2 < pg
    print("ok normal, media implicada y push")


def test_referencia_y_lados():
    ref = lm.referencia(vigilante.CANARIO_OBK_LINEAS, "spread", "nba")
    assert ref and ref["linea"] == -5.5 and ref["sd"] == 12.5
    assert 5.0 < ref["mu"] < 6.5, ref["mu"]            # Pinnacle 1.93/1.95: local ligeramente favorecido sobre -5.5
    # a la MISMA linea con precios peores (fanduel 1.91/1.91) no hay valor; gtbets en -3.5 (dos puntos) si
    home = lm.evaluar_lado(vigilante.CANARIO_OBK_LINEAS, "spread", "home", ref)
    assert home and home["bk"] == "gtbets" and home["linea_soft"] == -3.5, home
    assert home["n_misma_linea"] == 1 and home["median_misma_linea"] == 1.91, home   # solo gtbets esta en -3.5
    assert home["bet_type"] == "spread_home_-3.5" and 3.0 <= home["edge"] <= 12.0, home["edge"]
    away = lm.evaluar_lado(vigilante.CANARIO_OBK_LINEAS, "spread", "away", ref)
    assert away is None or away["bk"] == "bovada", away  # bovada -6.0 al visitante (+6) podria tener valor
    reft = lm.referencia(vigilante.CANARIO_OBK_LINEAS, "total", "nba")
    over = lm.evaluar_lado(vigilante.CANARIO_OBK_LINEAS, "total", "over", reft)
    assert over and over["bk"] == "fanduel" and over["linea_soft"] == 219.5
    assert over["bet_type"] == "total_points_over_219.5"
    under = lm.evaluar_lado(vigilante.CANARIO_OBK_LINEAS, "total", "under", reft)
    assert under is None, under
    # distancia maxima: una linea a 4 puntos no entra en spread
    obk = dict(vigilante.CANARIO_OBK_LINEAS)
    obk["lejos"] = {"spread_line": -1.5, "odds_spread_home": 2.5, "odds_spread_away": 1.5}
    h2 = lm.evaluar_lado(obk, "spread", "home", ref)
    assert h2["bk"] != "lejos"
    assert lm.lado_y_linea("spread_away_5.5") == ("spread", "away", 5.5)
    assert lm.lado_y_linea("total_points_under_215.0") == ("total", "under", 215.0)
    print("ok referencia, lados, bet_type y distancia maxima")


def _partido(db, ext, horas, liga="nba"):
    home = _find_or_create_team(db, f"Local {ext}", liga)
    away = _find_or_create_team(db, f"Visitante {ext}", liga)
    m = Match(external_id=ext, sport_key=f"basketball_{liga}", league=liga.upper(), league_tier=liga,
              home_team=home.name, away_team=away.name, home_team_id=home.id, away_team_id=away.id,
              commence_time=datetime.now(timezone.utc) + timedelta(hours=horas))
    db.add(m)
    db.flush()
    return m


def test_generate_picks_tres_mercados():
    db = SessionLocal()
    try:
        m = _partido(db, "v3-1", 3)
        for bk, d in vigilante.CANARIO_OBK.items():
            fila = dict(d)
            fila.update(vigilante.CANARIO_OBK_LINEAS.get(bk, {}))
            db.add(Odds(match_id=m.id, bookmaker=bk, **fila))
        for bk, d in vigilante.CANARIO_OBK_LINEAS.items():
            if bk not in vigilante.CANARIO_OBK:
                db.add(Odds(match_id=m.id, bookmaker=bk, odds_home=1.95, odds_away=1.95, **d))
        db.commit()
        n = value_calculator.generate_picks(db)
        picks = db.query(Pick).filter(Pick.match_id == m.id).all()
        tipos = sorted(p.bet_type for p in picks)
        assert n == 3 and len(picks) == 3, (n, tipos)
        assert tipos == ["match_winner_home", "spread_home_-3.5", "total_points_over_219.5"], tipos
        for p in picks:
            if p.bet_type.startswith("match_winner"):
                assert p.rule_version == RULE_VERSION and p.line_value is None
            else:
                assert p.rule_version == RULE_VERSION_LINES and p.is_shadow and p.line_value is not None
                assert p.ref_line in (-5.5, 221.5) and p.pinnacle_fair_at_pick and p.edge >= 3.0
                # mediana a la linea apostada: nunca por encima de la cuota cogida (cordura del vigilante)
                assert p.n_soft_books >= 1 and p.median_soft_odds <= p.best_odds + 1e-9, (p.bet_type, p.median_soft_odds, p.best_odds)
        # segunda pasada: no duplica (guard por mercado)
        assert value_calculator.generate_picks(db) == 0
    finally:
        db.close()
    print("ok generate_picks: ganador + handicap + total, sin duplicar")


def test_liquidacion_y_clv():
    db = SessionLocal()
    try:
        m = _partido(db, "v3-2", -3)
        m.commence_time = datetime.utcnow() - timedelta(hours=3)
        # cierre de Pinnacle 30 min antes: -7.0 / 224.5 (la linea se movio contra el local)
        t_close = m.commence_time - timedelta(minutes=30)
        db.add(OddsHistory(match_id=m.id, bookmaker="pinnacle", odds_home=1.5, odds_away=2.6,
                           spread_line=-7.0, odds_spread_home=1.92, odds_spread_away=1.96,
                           total_line=224.5, odds_over=1.93, odds_under=1.95, recorded_at=t_close))
        picks = [
            Pick(match_id=m.id, bet_type="spread_home_-4.5", best_odds=1.91, best_bookmaker="gtbets",
                 estimated_probability=0.55, edge=5.0, rule_version=RULE_VERSION_LINES, line_value=-4.5,
                 ref_line=-5.5, is_active=True, is_shadow=True, created_at=datetime.utcnow()),
            Pick(match_id=m.id, bet_type="spread_away_6.0", best_odds=1.91, best_bookmaker="bovada",
                 estimated_probability=0.5, edge=3.5, rule_version=RULE_VERSION_LINES, line_value=6.0,
                 ref_line=-5.5, is_active=True, is_shadow=True, created_at=datetime.utcnow()),
            Pick(match_id=m.id, bet_type="total_points_over_219.5", best_odds=1.91, best_bookmaker="fanduel",
                 estimated_probability=0.55, edge=4.0, rule_version=RULE_VERSION_LINES, line_value=219.5,
                 ref_line=221.5, is_active=True, is_shadow=True, created_at=datetime.utcnow()),
        ]
        for p in picks:
            db.add(p)
        db.commit()
        # resultado 110-104: margen 6 -> home -4.5 gana; away +6 -> push; total 214 -> over 219.5 pierde
        score_resolver.apply_final_score(db, m, {"points_home": 110, "points_away": 104})
        db.commit()
        res = {p.bet_type: (p.result, p.profit_units) for p in db.query(Pick).filter(Pick.match_id == m.id)}
        assert res["spread_home_-4.5"] == ("won", round(0.91, 4)), res
        assert res["spread_away_6.0"] == ("void", 0.0), res
        assert res["total_points_over_219.5"] == ("lost", -1.0), res
        # CLV de linea: home -4.5 contra cierre -7 -> +2.5 puntos; el cierre dice que el local era mas
        # favorito, asi que la cuota justa de Pinnacle a -4.5 es menor que 1.91 (CLV positivo)
        p_home = db.query(Pick).filter(Pick.match_id == m.id, Pick.bet_type == "spread_home_-4.5").first()
        assert p_home.closing_line == -7.0 and cerca(p_home.line_clv, 2.5), (p_home.closing_line, p_home.line_clv)
        assert p_home.clv_pct is not None and p_home.closing_odds is not None, (p_home.clv_pct, p_home.closing_odds)
        assert p_home.closing_odds < 1.91 and p_home.clv_pct > 0, (p_home.clv_pct, p_home.closing_odds)
        p_over = db.query(Pick).filter(Pick.match_id == m.id, Pick.bet_type == "total_points_over_219.5").first()
        assert p_over.closing_line == 224.5 and cerca(p_over.line_clv, 5.0) and p_over.clv_pct > 0
        print("ok liquidacion (gana / push / pierde) y CLV de linea:",
              f"home clv {p_home.clv_pct:+.1f}% linea {p_home.line_clv:+.1f}; over clv {p_over.clv_pct:+.1f}%")
    finally:
        db.close()


def test_paridad_ganador():
    """El canario del ganador (sin lineas) debe dar exactamente lo guardado antes de sharp-v3."""
    ruta = os.path.join(os.path.dirname(__file__), "canario_esperado.json")
    esperado = json.loads(open(ruta, encoding="utf-8").read())
    actual = vigilante.canario_calcular()
    for k in ("home", "away", "devig", "clv", "modelo"):
        assert json.dumps(actual[k], sort_keys=True) == json.dumps(esperado[k], sort_keys=True), k
    assert actual.get("spread_home") and actual.get("total_over")
    print("ok paridad del ganador con el canario anterior; canario de lineas presente")


if __name__ == "__main__":
    init_db()
    test_normal_y_push()
    test_referencia_y_lados()
    test_generate_picks_tres_mercados()
    test_liquidacion_y_clv()
    test_paridad_ganador()
    print("TODO OK")
