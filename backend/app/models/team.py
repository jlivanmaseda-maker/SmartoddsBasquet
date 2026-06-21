"""Modelo de Equipo de Basket.

Reemplaza al modelo Player de tenis. En basket el "competidor" es un equipo,
con ELO global + ELO local/visitante, rating ofensivo/defensivo (Net Rating),
forma reciente y contexto de descanso (back-to-back).
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float
from app.db.database import Base


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(100), index=True, nullable=True)  # id de la API
    name = Column(String(200), nullable=False, index=True)
    short_name = Column(String(50), nullable=True)                # "LAL", "BOS"
    league = Column(String(50), nullable=True)                    # "nba","euroleague","acb"
    country = Column(String(50), nullable=True)
    conference = Column(String(50), nullable=True)                # "East"/"West" (NBA)

    # ELO ratings
    elo_overall = Column(Float, default=1500.0)
    elo_home = Column(Float, default=1500.0)                      # rendimiento como local
    elo_away = Column(Float, default=1500.0)                      # rendimiento como visitante
    games_total = Column(Integer, default=0)

    # Ratings avanzados (por 100 posesiones)
    offensive_rating = Column(Float, nullable=True)               # ORtg
    defensive_rating = Column(Float, nullable=True)               # DRtg
    net_rating = Column(Float, nullable=True)                     # ORtg - DRtg
    pace = Column(Float, nullable=True)                           # posesiones por 48 min

    # Forma reciente
    win_rate_last_10 = Column(Float, nullable=True)
    win_rate_season = Column(Float, nullable=True)
    points_for_avg = Column(Float, nullable=True)
    points_against_avg = Column(Float, nullable=True)

    # Contexto / fatiga
    last_game_date = Column(DateTime, nullable=True)
    games_last_7d = Column(Integer, default=0)

    # Ranking / standings
    current_rank = Column(Integer, nullable=True)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TeamNameAlias(Base):
    """Alias de nombres de equipo para casar fuentes distintas.

    Igual que players_name_aliases en tenis: "LA Lakers", "Los Angeles Lakers",
    "Lakers" -> mismo team_id. source = odds_api | betsapi | betburger.
    """
    __tablename__ = "teams_name_aliases"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, index=True, nullable=False)
    alias = Column(String(200), unique=True, nullable=False)
    source = Column(String(50), nullable=True)
