"""Reenlaza los partidos de NBA a equipos propios de la liga "nba" (19-oct-2026).

Antes `_find_or_create_team` buscaba solo por nombre, asi que los partidos de la
NBA 2026-27 quedaron enlazados a los equipos de la Summer League (tier nba_sl,
mismo nombre de franquicia, otro ELO). Este script crea los equipos "nba" que
falten y cambia home_team_id / away_team_id de los partidos con league_tier
"nba". No toca ELO ni resultados.

Dry-run por defecto; --apply escribe. Uso (VPS):
  cd /opt/SmartOddsBasketball/backend
  venv/bin/python ../scripts/fix_nba_teams.py [--apply]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.db.database import SessionLocal  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.models.team import Team  # noqa: E402
from app.services.odds_fetcher import _find_or_create_team  # noqa: E402

LEAGUE = "nba"


def main(apply: bool) -> int:
    db = SessionLocal()
    try:
        matches = db.query(Match).filter(Match.league_tier == LEAGUE).all()
        teams = {t.id: t for t in db.query(Team).all()}
        cambios = 0
        for m in matches:
            for attr, name in (("home_team_id", m.home_team), ("away_team_id", m.away_team)):
                actual = teams.get(getattr(m, attr))
                if actual is not None and actual.league == LEAGUE:
                    continue
                nuevo = _find_or_create_team(db, name, LEAGUE)
                teams[nuevo.id] = nuevo
                print(f"  match #{m.id} {m.home_team} vs {m.away_team} ({str(m.commence_time)[:10]}): "
                      f"{attr} {getattr(m, attr)} ({actual.league if actual else None}) -> {nuevo.id} ({LEAGUE})")
                setattr(m, attr, nuevo.id)
                cambios += 1
        n_teams = db.query(Team).filter(Team.league == LEAGUE).count()
        print(f"{len(matches)} partidos {LEAGUE}, {cambios} enlaces a cambiar, {n_teams} equipos {LEAGUE} tras el cambio")
        if apply and cambios:
            db.commit()
            print("APLICADO")
        else:
            db.rollback()
            print("dry-run: nada escrito" if not apply else "nada que cambiar")
        return cambios
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
