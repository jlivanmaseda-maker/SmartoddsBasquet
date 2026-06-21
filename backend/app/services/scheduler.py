"""Scheduler — orquesta el ciclo principal con APScheduler.

Portado de tenis (simplificado). Dos jobs:

  ODDS  (cada ODDS_UPDATE_INTERVAL_MINUTES):
     odds_fetcher.fetch_all()  -> Match + Team + Odds
     value_calculator.generate_picks()  -> Pick (edge >= MIN_EDGE; shadow si toca)

  SCORES (cada SCORES_UPDATE_INTERVAL_MINUTES):
     score_resolver.resolve_completed()  -> liquida picks (won/lost/void)
     _update_elo_pass()  -> actualiza ELO de equipo una vez por partido

Semanal (lunes): TODO simulated_annealing.optimize_weights() cuando haya datos.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.db.database import SessionLocal
from app.models.match import Match
from app.models.team import Team

logger = logging.getLogger("smartodds_basketball.scheduler")


def _job_odds():
    """Ciclo de odds: fetch (The Odds API + BetsAPI) + generacion de picks."""
    from app.services import odds_fetcher, value_calculator
    db = SessionLocal()
    try:
        summary = odds_fetcher.fetch_all(db)
        logger.info(f"[ODDS] TheOddsAPI {summary}")
    except Exception as e:
        logger.error(f"[ODDS] fetch_all error: {e}", exc_info=True)
    finally:
        db.close()
    # BetsAPI: ligas fuera de The Odds API (ACB, etc.). Opcional/best-effort.
    try:
        from app.services import betsapi_odds_fetcher
        bsummary = betsapi_odds_fetcher.fetch_all()
        logger.info(f"[ODDS] BetsAPI {bsummary}")
    except ImportError:
        pass
    except Exception as e:
        logger.error(f"[ODDS] betsapi fetch error: {e}", exc_info=True)
    try:
        n = value_calculator.generate_picks()
        logger.info(f"[ODDS] {n} picks generados")
    except Exception as e:
        logger.error(f"[ODDS] generate_picks error: {e}", exc_info=True)


def _job_scores():
    """Ciclo de scores: resolucion + actualizacion de ELO."""
    from app.services import score_resolver
    db = SessionLocal()
    try:
        n = score_resolver.resolve_completed(db)
        if n:
            logger.info(f"[SCORES] {n} partidos resueltos")
    except Exception as e:
        logger.error(f"[SCORES] resolve_completed error: {e}", exc_info=True)
    finally:
        db.close()
    _update_elo_pass()


def _update_elo_pass():
    """Actualiza el ELO de equipo para partidos completados aun sin aplicar."""
    from app.ml.elo_calculator import update_after_game
    db = SessionLocal()
    applied = 0
    try:
        matches = db.query(Match).filter(
            Match.is_completed == True,            # noqa: E712
            Match.elo_applied == False,            # noqa: E712
            Match.is_postponed == False,           # noqa: E712
        ).all()
        for m in matches:
            if m.points_home is None or m.points_away is None:
                continue
            home = db.query(Team).filter(Team.id == m.home_team_id).first()
            away = db.query(Team).filter(Team.id == m.away_team_id).first()
            if not home or not away:
                m.elo_applied = True
                continue
            home_won = m.points_home > m.points_away
            margin = abs(m.points_home - m.points_away)
            update_after_game(home, away, home_won, m.league_tier or "", margin)
            m.elo_applied = True
            applied += 1
        if applied:
            db.commit()
            logger.info(f"[ELO] actualizado para {applied} partidos")
        else:
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[ELO] update pass error: {e}", exc_info=True)
    finally:
        db.close()


class OddsScheduler:
    """Gestiona los jobs periodicos con APScheduler."""

    def __init__(self):
        self._scheduler = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._scheduler = BackgroundScheduler(timezone="UTC")
        # NOTA: NO pasar next_run_time=None (APScheduler dejaria el job en pausa).
        # Sin ese arg, el primer disparo es a now + intervalo.
        self._scheduler.add_job(
            _job_odds, "interval",
            minutes=settings.ODDS_UPDATE_INTERVAL_MINUTES,
            id="odds", max_instances=1, coalesce=True,
        )
        self._scheduler.add_job(
            _job_scores, "interval",
            minutes=settings.SCORES_UPDATE_INTERVAL_MINUTES,
            id="scores", max_instances=1, coalesce=True,
        )
        self._scheduler.start()
        self._running = True
        logger.info(
            f"Scheduler arrancado (odds={settings.ODDS_UPDATE_INTERVAL_MINUTES}min, "
            f"scores={settings.SCORES_UPDATE_INTERVAL_MINUTES}min)"
        )

    def stop(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Scheduler detenido")

    def run_odds_now(self):
        """Disparo manual del ciclo de odds (util para pruebas)."""
        _job_odds()

    def get_service_status(self) -> dict:
        jobs = []
        if self._scheduler:
            for j in self._scheduler.get_jobs():
                jobs.append({
                    "id": j.id,
                    "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
                })
        return {"running": self._running, "jobs": jobs}


odds_scheduler = OddsScheduler()
