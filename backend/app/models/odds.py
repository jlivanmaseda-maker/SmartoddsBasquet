"""Modelos de cuotas (snapshot actual + historico)."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey
from app.db.database import Base


class Odds(Base):
    __tablename__ = "odds"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    bookmaker = Column(String(50), nullable=False, index=True)

    # Moneyline (Match Winner) — 2 vias
    odds_home = Column(Float, nullable=True)
    odds_away = Column(Float, nullable=True)

    # Spread (Hándicap de puntos)
    spread_line = Column(Float, nullable=True)            # -5.5
    odds_spread_home = Column(Float, nullable=True)
    odds_spread_away = Column(Float, nullable=True)

    # Totals (Over/Under puntos)
    total_line = Column(Float, nullable=True)             # 215.5
    odds_over = Column(Float, nullable=True)
    odds_under = Column(Float, nullable=True)

    # Flags de valor
    is_value_home = Column(Boolean, default=False)
    is_value_away = Column(Boolean, default=False)

    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OddsHistory(Base):
    __tablename__ = "odds_history"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    bookmaker = Column(String(50), nullable=False)

    odds_home = Column(Float, nullable=True)
    odds_away = Column(Float, nullable=True)
    spread_line = Column(Float, nullable=True)
    odds_spread_home = Column(Float, nullable=True)
    odds_spread_away = Column(Float, nullable=True)
    total_line = Column(Float, nullable=True)
    odds_over = Column(Float, nullable=True)
    odds_under = Column(Float, nullable=True)

    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)
