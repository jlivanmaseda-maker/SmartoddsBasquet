"""Modelo de Partido de Basket.

Adaptado de tenis: equipos en vez de jugadores, puntos/cuartos en vez de
sets/games. No hay empate (moneyline a 2 vias); el desempate es la prorroga
(overtime), no una retirada.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey
from app.db.database import Base


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)

    # Identificador externo (de The Odds API / BetsAPI con prefijo "betsapi_")
    external_id = Column(String(100), unique=True, index=True, nullable=False)

    # Liga
    sport_key = Column(String(100), nullable=True)      # "basketball_nba"
    league = Column(String(200), nullable=True)          # "NBA", "EuroLeague", "ACB"
    league_tier = Column(String(50), nullable=True)      # "nba","euroleague","ncaab","wnba"
    season = Column(String(20), nullable=True)           # "2025-26"
    stage = Column(String(50), nullable=True)            # "regular","playoffs","final_four"

    # Equipos
    home_team = Column(String(200), nullable=False)      # Local
    away_team = Column(String(200), nullable=False)      # Visitante
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=True, index=True)

    # Fecha y estado
    commence_time = Column(DateTime, nullable=False)
    is_live = Column(Boolean, default=False)
    is_completed = Column(Boolean, default=False)

    # Resultado
    score = Column(String(50), nullable=True)            # "112-104"
    points_home = Column(Integer, nullable=True)         # Puntos local
    points_away = Column(Integer, nullable=True)         # Puntos visitante
    total_points = Column(Integer, nullable=True)        # Suma (para mercado totals)
    is_overtime = Column(Boolean, default=False)         # Hubo prorroga
    overtimes = Column(Integer, nullable=True)           # Numero de prorrogas
    is_postponed = Column(Boolean, default=False)        # Aplazado/cancelado = void

    # Probabilidades estimadas por nuestro modelo
    prob_home = Column(Float, nullable=True)             # Prob gane local
    prob_away = Column(Float, nullable=True)             # Prob gane visitante
    # (NO hay prob_draw — en basket no hay empate, se juega prorroga)

    # Linea y probabilidades para mercados shadow
    spread_line = Column(Float, nullable=True)           # Hándicap puntos: -5.5
    prob_cover_home = Column(Float, nullable=True)       # Prob local cubre spread
    total_line = Column(Float, nullable=True)            # Linea totals: 215.5
    prob_over_total = Column(Float, nullable=True)       # Prob over puntos

    # Cuota Minima Rentable
    cmin_home = Column("min_odds_home", Float, nullable=True)
    cmin_away = Column("min_odds_away", Float, nullable=True)

    # Contexto de descanso (clave en basket: back-to-back, dias de descanso)
    home_rest_days = Column(Integer, nullable=True)
    away_rest_days = Column(Integer, nullable=True)
    home_back_to_back = Column(Boolean, default=False)
    away_back_to_back = Column(Boolean, default=False)

    # Modelo
    model_source = Column(String(100), nullable=True)
    model_confidence = Column(Float, nullable=True)

    # ELO ya aplicado tras la resolucion (evita doble update del rating)
    elo_applied = Column(Boolean, default=False)

    # Meta
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
