"""Pruebas de la API de la pagina /picks (shadowRules, shadowPicks, systemStatus; 25-oct-2026). Sin pytest:

  cd backend && python ../scripts/test_web_sombra.py

BD SQLite temporal: un pick de ganador abierto con cuotas de varias casas y uno de handicap de visitante ya
liquidado. Comprueba el resumen por regla (ROI, mediana, CLV, linea), el texto de la apuesta, la cuota minima
(con push en las lineas), las casas que la pagan ahora y el estado del vigilante leido de su fichero.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

_tmp = tempfile.mkdtemp(prefix="basquet_web_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "test.db").replace("\\", "/")
os.environ["BASKET_VIGILANTE_ESTADO"] = os.path.join(_tmp, "vigilante_estado.json")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.database import SessionLocal, init_db  # noqa: E402
from app.models.bet import Pick  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.models.odds import Odds  # noqa: E402
from app.schemas import sombra  # noqa: E402
from app.schemas.graphql_schema import schema  # noqa: E402


def preparar():
    init_db()
    db = SessionLocal()
    ahora = datetime.utcnow()
    m1 = Match(external_id="w1", sport_key="basketball_nba", league="NBA", league_tier="nba", home_team="Local A",
               away_team="Visitante B", commence_time=ahora + timedelta(hours=5))
    m2 = Match(external_id="w2", sport_key="basketball_nba", league="NBA", league_tier="nba", home_team="Local C",
               away_team="Visitante D", commence_time=ahora - timedelta(hours=10), is_completed=True,
               score="100-110", points_home=100, points_away=110)
    db.add_all([m1, m2])
    db.flush()
    for bk, oh, oa in (("pinnacle", 1.80, 2.10), ("fanduel", 2.00, 1.80), ("bovada", 1.90, 1.90),
                       ("betfair_ex_eu", 2.20, 1.70)):
        db.add(Odds(match_id=m1.id, bookmaker=bk, odds_home=oh, odds_away=oa))
    db.add(Pick(match_id=m1.id, bet_type="match_winner_home", best_odds=2.00, best_bookmaker="fanduel",
                estimated_probability=0.54, edge=8.0, median_soft_odds=1.95, n_soft_books=2,
                pinnacle_fair_at_pick=1.85, rule_version="sharp-v2", is_active=True, is_shadow=True,
                created_at=ahora - timedelta(hours=2)))
    db.add(Pick(match_id=m2.id, bet_type="spread_away_6.0", best_odds=1.91, best_bookmaker="coolbet",
                estimated_probability=0.52, edge=4.0, median_soft_odds=1.88, n_soft_books=4,
                pinnacle_fair_at_pick=1.85, line_value=6.0, ref_line=-4.5, closing_line=-4.0, line_clv=2.0,
                clv_pct=6.5, closing_odds=1.79, rule_version="sharp-v3", result="won", profit_units=0.91,
                is_active=False, is_shadow=True, created_at=ahora - timedelta(hours=30),
                resolved_at=ahora - timedelta(hours=7)))
    db.commit()
    db.close()
    with open(os.environ["BASKET_VIGILANTE_ESTADO"], "w", encoding="utf-8") as f:
        json.dump({"servicio": {"ok": True}, "cordura": {"ok": False, "texto": "cordura: aviso de prueba"}}, f)


def test_api():
    q = """{ systemStatus { reglaGanador reglaLineas vigilanteOk vigilanteFallos }
      shadowRules { clave picks abiertos liquidados ganados roi roiMediana clv lineaVsCierre objetivo cumpleUmbral }
      shadowPicks { clave seleccion estado cuota cuotaMinima casas { casa cuota } lineaVsCierre }
      abiertos: shadowPicks(estado: "abiertos") { id }
      v3: shadowPicks(clave: "sharp-v3|handicap") { seleccion } }"""
    r = schema.execute_sync(q)
    assert not r.errors, r.errors
    d = r.data
    s = d["systemStatus"]
    assert s["vigilanteOk"] is False and s["vigilanteFallos"] == ["cordura: aviso de prueba"], s
    reglas = {x["clave"]: x for x in d["shadowRules"]}
    assert set(reglas) == {"sharp-v2|ganador", "sharp-v3|handicap"}, reglas
    g, h = reglas["sharp-v2|ganador"], reglas["sharp-v3|handicap"]
    assert g["picks"] == 1 and g["abiertos"] == 1 and g["liquidados"] == 0 and g["roi"] is None
    assert h["liquidados"] == 1 and h["ganados"] == 1 and h["roi"] == 91.0 and h["roiMediana"] == 88.0, h
    assert h["clv"] == 6.5 and h["lineaVsCierre"] == 2.0 and h["objetivo"] == 300 and not h["cumpleUmbral"]
    picks = {x["clave"]: x for x in d["shadowPicks"]}
    pg, ph = picks["sharp-v2|ganador"], picks["sharp-v3|handicap"]
    assert pg["seleccion"] == "Gana Local A" and pg["estado"] == "abierto"
    assert pg["cuotaMinima"] == round(1.03 / 0.54, 2), pg["cuotaMinima"]          # 1,91
    assert [c["casa"] for c in pg["casas"]] == ["fanduel", "bovada"], pg["casas"]  # sin Pinnacle ni exchanges
    assert ph["seleccion"] == "Visitante D +6.0" and ph["estado"] == "ganado" and ph["casas"] == []
    p_push = 1 - 1.85 * 0.52
    assert ph["cuotaMinima"] == round((1.03 - p_push) / 0.52, 2), ph["cuotaMinima"]
    assert len(d["abiertos"]) == 1 and [x["seleccion"] for x in d["v3"]] == ["Visitante D +6.0"]
    assert sombra.seleccion("total_points_under_221.5", "A", "B") == "Menos de 221.5 puntos"
    assert sombra.seleccion("spread_home_-3.5", "A", "B") == "A -3.5"
    print("ok shadowRules, shadowPicks y systemStatus")


if __name__ == "__main__":
    preparar()
    test_api()
    print("TODO OK")
