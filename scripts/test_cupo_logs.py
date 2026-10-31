"""Pruebas de las correcciones tras el corte por cupo agotado del 31-oct-2026. Sin pytest ni red:

  cd backend && python ../scripts/test_cupo_logs.py

Respuestas de The Odds API simuladas con httpx.MockTransport y BD SQLite temporal. Comprueba: un fallo de /scores no
anula picks aunque el partido pase de 72 h; tampoco tras volver la API si el fallo fue despues del inicio; un aplazado
de verdad se sigue anulando; el resultado se liquida al volver; 401 de cupo y de clave se distinguen; el cupo a 0 se
anota; y ni la clave ni el token de Telegram llegan al log.
"""
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_tmp = tempfile.mkdtemp(prefix="basquet_cupo_")
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "test.db").replace("\\", "/")
os.environ["LOG_DIR"] = _tmp
os.environ["ODDS_API_KEY"] = "CLAVESECRETA123"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.logging_config import redactar, setup_logging  # noqa: E402

setup_logging()

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.models.bet import Pick  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.services import odds_fetcher, score_resolver as sr  # noqa: E402

settings.ODDS_API_KEY = "CLAVESECRETA123"
LOG = os.path.join(_tmp, "app.log")
_ClientReal = httpx.Client


def api(respuesta):
    """Sustituye httpx.Client para que cada peticion reciba `respuesta(request)`."""
    def cliente(**kw):
        return _ClientReal(transport=httpx.MockTransport(respuesta), **kw)
    httpx.Client = cliente


def cupo_agotado(request):
    return httpx.Response(401, json={"message": "Usage quota has been reached.", "error_code": "OUT_OF_USAGE_CREDITS"},
                          headers={"x-requests-remaining": "0", "x-requests-used": "1000000"})


def partido(db, ext, horas_atras):
    m = Match(external_id=ext, sport_key="basketball_nba", league="NBA", league_tier="nba", home_team=f"L {ext}",
              away_team=f"V {ext}", commence_time=datetime.utcnow() - timedelta(hours=horas_atras))
    db.add(m)
    db.flush()
    db.add(Pick(match_id=m.id, bet_type="match_winner_home", best_odds=2.0, best_bookmaker="fanduel", edge=5.0,
                estimated_probability=0.55, rule_version="sharp-v2", is_active=True, is_shadow=True,
                created_at=datetime.utcnow() - timedelta(hours=horas_atras + 2)))
    db.commit()
    return m.id


def estado(db, mid):
    db.expire_all()
    m = db.get(Match, mid)
    p = db.query(Pick).filter(Pick.match_id == mid).first()
    return bool(m.is_completed), bool(m.is_postponed), p.result


def test_resultados():
    db = SessionLocal()
    # 1) cupo agotado: partido de hace 80 h (pasa la guarda de 72 h): NO se anula
    mid = partido(db, "viejo", 80)
    api(cupo_agotado)
    assert sr._fetch_odds_api_scores("basketball_nba") is None
    assert sr.resolve_completed(db) == 0
    assert estado(db, mid) == (False, False, None), estado(db, mid)
    # 2) vuelve la API pero el partido ya no esta en /scores: como fallo despues del inicio, tampoco se anula
    api(lambda r: httpx.Response(200, json=[]))
    assert sr._fetch_odds_api_scores("basketball_nba") == {}
    assert sr.resolve_completed(db) == 0
    assert estado(db, mid) == (False, False, None), estado(db, mid)
    # 3) aplazado de verdad: empezo DESPUES del ultimo fallo y lleva 80 h sin resultado: se anula como siempre
    sr._ULTIMO_FALLO_SCORES["basketball_nba"] = datetime.now(timezone.utc) - timedelta(hours=100)
    assert sr.resolve_completed(db) == 1
    assert estado(db, mid) == (True, True, "void"), estado(db, mid)
    # 4) al volver la API, un partido con resultado se liquida con normalidad
    sr._ULTIMO_FALLO_SCORES["basketball_nba"] = datetime.now(timezone.utc)
    mid2 = partido(db, "reciente", 5)
    api(lambda r: httpx.Response(200, json=[{"id": "reciente", "completed": True, "home_team": "L reciente",
                                             "away_team": "V reciente", "scores": [
                                                 {"name": "L reciente", "score": "101"},
                                                 {"name": "V reciente", "score": "99"}]}]))
    assert sr.resolve_completed(db) == 1
    assert estado(db, mid2) == (True, False, "won"), estado(db, mid2)
    # 5) recien empezado y sin datos: sigue la guarda de 72 h
    sr._ULTIMO_FALLO_SCORES.clear()
    mid3 = partido(db, "guarda", 10)
    api(lambda r: httpx.Response(200, json=[]))
    assert sr.resolve_completed(db) == 0
    assert estado(db, mid3) == (False, False, None), estado(db, mid3)
    db.close()
    print("ok un fallo de /scores no anula picks; los aplazados de verdad, si; al volver se liquida")


def test_401():
    assert "cupo" in odds_fetcher.describir_401(cupo_agotado(None))
    mala = httpx.Response(401, json={"message": "API key is invalid", "error_code": "INVALID_KEY"})
    assert "invalida" in odds_fetcher.describir_401(mala) and "INVALID_KEY" in odds_fetcher.describir_401(mala)
    assert "invalida" in odds_fetcher.describir_401(httpx.Response(401, text="no es json"))
    api(cupo_agotado)
    odds_fetcher.LAST_CREDITS.update(remaining=None, used=None)
    assert odds_fetcher.fetch_league_odds("basketball_nba") == []
    assert odds_fetcher.LAST_CREDITS["remaining"] == "0" and odds_fetcher.LAST_CREDITS["used"] == "1000000"
    print("ok cupo agotado y clave mala se distinguen; el cupo a 0 queda anotado")


def test_logs():
    assert redactar("GET https://a/b?apiKey=XYZ&regions=eu") == "GET https://a/b?apiKey=***&regions=eu"
    assert redactar("https://api.telegram.org/bot123:ABC-d_e/sendMessage") == "https://api.telegram.org/bot***/sendMessage"
    assert redactar("a?token=XYZ daysFrom=3") == "a?token=*** daysFrom=3"
    # peticion real de httpx (a INFO escribiria la URL), mensaje con la clave, argumentos y traza de un error
    api(lambda r: httpx.Response(200, json=[]))
    with httpx.Client() as c:
        c.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": "CLAVESECRETA123"})
    log = logging.getLogger("smartodds_basketball.prueba")
    log.error("fallo en https://x/y?apiKey=CLAVESECRETA123&a=1")
    log.warning("con argumento %s", "https://x/y?apiKey=CLAVESECRETA123")
    log.info("telegram https://api.telegram.org/bot999:TOKENSECRETO/sendMessage")
    try:
        raise RuntimeError("https://x/y?apiKey=CLAVESECRETA123")
    except RuntimeError:
        log.exception("error con traza")
    log.info("linea normal 123")
    for h in logging.getLogger().handlers:
        h.flush()
    texto = open(LOG, encoding="utf-8").read()
    assert "CLAVESECRETA123" not in texto, "la clave ha llegado al log"
    assert "TOKENSECRETO" not in texto, "el token ha llegado al log"
    assert "linea normal 123" in texto and "error con traza" in texto and "RuntimeError" in texto, texto[-400:]
    assert "api.the-odds-api.com" not in texto, "httpx sigue escribiendo sus peticiones"
    print("ok ni la clave ni el token llegan al log, y el resto de lineas siguen")


if __name__ == "__main__":
    init_db()
    test_logs()
    test_401()
    test_resultados()
    print("TODO OK")
