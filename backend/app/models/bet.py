"""Modelos de Picks (sistema) y UserBets (apuestas del usuario)."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey
from app.db.database import Base


class Pick(Base):
    __tablename__ = "picks"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)

    # bet_type: "match_winner_home", "match_winner_away",
    #           "spread_home_-5.5", "total_points_over_215.5"
    bet_type = Column(String(100), nullable=False)

    cmin = Column("min_odds", Float, nullable=True)
    best_odds = Column(Float, nullable=True)
    best_bookmaker = Column(String(50), nullable=True)
    estimated_probability = Column(Float, nullable=True)
    edge = Column(Float, nullable=True)

    is_active = Column(Boolean, default=True)
    is_live = Column(Boolean, default=False)
    is_shadow = Column(Boolean, default=False)
    shadow_reasons = Column(String(500), nullable=True)  # auditoria: "no_sharp,ncaab"

    # Resultado
    result = Column(String(20), nullable=True)           # "won","lost","void"
    profit_units = Column(Float, nullable=True)

    # CLV (Closing Line Value)
    closing_odds = Column(Float, nullable=True)
    closing_bookmaker = Column(String(50), nullable=True)
    pinnacle_closing_odds = Column(Float, nullable=True)
    clv_pct = Column(Float, nullable=True)

    # Senales sharp
    bookdif = Column(Float, nullable=True)
    sharp_odds = Column(Float, nullable=True)
    dispersion = Column(Float, nullable=True)            # (max_odds/avgline - 1) * 100

    priority_score = Column(Float, nullable=True)        # edge * probabilidad

    # Medicion como en TT (19-oct-2026): version de la regla que creo el pick
    # (cada regla se mide desde su hora de despliegue), mediana de las casas
    # blandas y cuota de Pinnacle (cruda y sin margen) en el instante del pick.
    rule_version = Column(String(40), nullable=True)
    median_soft_odds = Column(Float, nullable=True)
    n_soft_books = Column(Integer, nullable=True)
    pinnacle_odds_at_pick = Column(Float, nullable=True)
    pinnacle_fair_at_pick = Column(Float, nullable=True)

    # sharp-v3 (20-oct-2026): mercados de linea. line_value = linea apostada (convencion del
    # bet_type); ref_line = linea de Pinnacle al crear el pick; closing_line = linea de Pinnacle
    # al cierre; line_clv = puntos ganados frente al cierre (positivo = mejor linea que el cierre).
    line_value = Column(Float, nullable=True)
    ref_line = Column(Float, nullable=True)
    closing_line = Column(Float, nullable=True)
    line_clv = Column(Float, nullable=True)

    # Track record publico (firma HMAC verificable) — opcional, como en tenis
    public_id = Column(String(64), nullable=True, index=True)
    is_public = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)


class UserBet(Base):
    __tablename__ = "user_bets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pick_id = Column(Integer, ForeignKey("picks.id"), nullable=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True, index=True)

    bookmaker = Column(String(50), nullable=True)
    odds = Column(Float, nullable=True)
    stake = Column(Float, nullable=True)
    bet_type = Column(String(100), nullable=True)

    result = Column(String(20), nullable=True)
    profit = Column(Float, nullable=True)

    placed_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class PickModelDetail(Base):
    """Desglose de las probabilidades por componente del ensemble (auditoria)."""
    __tablename__ = "pick_model_details"

    id = Column(Integer, primary_key=True, index=True)
    pick_id = Column(Integer, ForeignKey("picks.id"), nullable=False, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True, index=True)

    elo_team_prob = Column(Float, nullable=True)
    net_rating_prob = Column(Float, nullable=True)
    form_prob = Column(Float, nullable=True)
    rest_adjustment = Column(Float, nullable=True)
    home_court_adjustment = Column(Float, nullable=True)
    h2h_prob = Column(Float, nullable=True)
    ensemble_prob = Column(Float, nullable=True)
