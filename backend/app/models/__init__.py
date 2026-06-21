"""Modelos ORM. Importar todos aqui para que init_db() cree las tablas."""
from app.models.match import Match  # noqa: F401
from app.models.team import Team, TeamNameAlias  # noqa: F401
from app.models.odds import Odds, OddsHistory  # noqa: F401
from app.models.bet import Pick, UserBet, PickModelDetail  # noqa: F401
from app.models.user import User  # noqa: F401
