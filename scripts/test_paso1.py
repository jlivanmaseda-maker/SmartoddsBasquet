"""Pruebas del paso 1 (19-oct-2026) sobre una BD SQLite temporal. Sin pytest:

  cd backend && python ../scripts/test_paso1.py

Comprueba: equipos por liga (mismo nombre, dos ligas -> dos equipos), columnas
nuevas del pick tras la migracion, mediana/Pinnacle/version en el pick que crea
generate_picks, canario del vigilante y decidir() del vigilante.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_tmp = tempfile.mkdtemp(prefix="basquet_test_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "test.db").replace("\\", "/")
os.environ["BASKET_LOGS"] = _tmp
os.environ["BASKET_VIGILANTE_ESTADO"] = os.path.join(_tmp, "estado.json")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import inspect  # noqa: E402

from app.db.database import SessionLocal, engine, init_db  # noqa: E402
from app.models.bet import Pick  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.models.odds import Odds  # noqa: E402
from app.models.team import Team  # noqa: E402
from app.services.odds_fetcher import _find_or_create_team  # noqa: E402
from app.services import value_calculator  # noqa: E402
from app.version import RULE_VERSION  # noqa: E402

import vigilante  # noqa: E402


def test_equipos_por_liga():
    db = SessionLocal()
    try:
        a = _find_or_create_team(db, "Los Angeles Lakers", "nba_sl")
        b = _find_or_create_team(db, "Los Angeles Lakers", "nba")
        c = _find_or_create_team(db, "Los Angeles Lakers", "nba")
        db.commit()
        assert a.id != b.id, "mismo nombre en dos ligas debe dar dos equipos"
        assert b.id == c.id, "la segunda busqueda en la misma liga reutiliza el equipo"
        assert db.query(Team).filter(Team.name == "Los Angeles Lakers").count() == 2
    finally:
        db.close()
    print("ok equipos por liga")


def test_columnas_pick():
    cols = {c["name"] for c in inspect(engine).get_columns("picks")}
    for c in ("rule_version", "median_soft_odds", "n_soft_books", "pinnacle_odds_at_pick", "pinnacle_fair_at_pick"):
        assert c in cols, f"falta la columna {c}"
    print("ok columnas del pick")


def test_generate_picks_guarda_mediana():
    db = SessionLocal()
    try:
        home = _find_or_create_team(db, "Equipo A", "wnba")
        away = _find_or_create_team(db, "Equipo B", "wnba")
        now = datetime.now(timezone.utc)
        m = Match(external_id="test-1", sport_key="basketball_wnba", league="WNBA", league_tier="wnba",
                  home_team="Equipo A", away_team="Equipo B", home_team_id=home.id, away_team_id=away.id,
                  commence_time=now + timedelta(hours=3))
        db.add(m)
        db.flush()
        for bk, d in vigilante.CANARIO_OBK.items():
            db.add(Odds(match_id=m.id, bookmaker=bk, odds_home=d["odds_home"], odds_away=d["odds_away"]))
        db.commit()
        n = value_calculator.generate_picks(db)
        assert n == 1, f"esperaba 1 pick, salieron {n}"
        p = db.query(Pick).filter(Pick.match_id == m.id).first()
        assert p.rule_version == RULE_VERSION
        assert p.bet_type == "match_winner_home", p.bet_type
        assert p.best_odds == 2.00 and p.best_bookmaker == "fanduel"
        # blandas del lado local: 1.95, 2.00, 1.91, 1.93, 1.97 -> mediana 1.95 (exchange fuera)
        assert p.median_soft_odds == 1.95, p.median_soft_odds
        assert p.n_soft_books == 5, p.n_soft_books
        assert p.pinnacle_odds_at_pick == 1.87
        assert abs(p.pinnacle_fair_at_pick - round(1 / ((1 / 1.87) / (1 / 1.87 + 1 / 2.05)), 4)) < 1e-9
        assert p.median_soft_odds <= p.best_odds
    finally:
        db.close()
    print("ok generate_picks guarda mediana, Pinnacle y version")


def test_canario():
    d = vigilante.canario_calcular()
    assert d["home"] is not None and d["home"]["best_odds"] == 2.00
    assert d["away"] is None, "el lado visitante no debe dar pick con estas cuotas"
    ok, texto = vigilante.check_canario()
    assert ok, texto
    print("ok canario:", texto)


def test_decidir():
    t0 = datetime(2026, 10, 20, 9, 0)
    lineas, est = vigilante.decidir({}, {"a": (False, "a: mal"), "b": (True, "b: ok")}, t0)
    assert lineas == ["MAL a: mal"], lineas
    lineas, est = vigilante.decidir(est, {"a": (False, "a: mal"), "b": (True, "b: ok")}, t0 + timedelta(hours=1))
    assert lineas == [], "sin recordatorio antes de RECORDAR_H"
    lineas, est = vigilante.decidir(est, {"a": (False, "a: mal"), "b": (True, "b: ok")}, t0 + timedelta(hours=7))
    assert len(lineas) == 1 and lineas[0].startswith("SIGUE MAL"), lineas
    lineas, est = vigilante.decidir(est, {"a": (True, "a: ok"), "b": (False, "b: mal")}, t0 + timedelta(hours=8))
    assert lineas == ["OK vuelve: a: mal", "MAL b: mal"], lineas
    print("ok decidir")


if __name__ == "__main__":
    init_db()
    test_equipos_por_liga()
    test_columnas_pick()
    test_generate_picks_guarda_mediana()
    test_canario()
    test_decidir()
    print("TODO OK")
