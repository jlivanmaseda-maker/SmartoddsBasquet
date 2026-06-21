"""Modelo de Usuario (auth + suscripcion). Identico a tenis."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    role = Column(String(20), default="user")            # "user" | "admin"

    # Bankroll / staking
    bankroll = Column(Float, default=1000.0)
    currency = Column(String(10), default="EUR")
    auto_bankroll = Column(Boolean, default=False)
    kelly_fraction = Column(Float, nullable=True)
    bookmakers = Column(String, nullable=True)            # CSV de casas elegidas

    # Estado
    is_active = Column(Boolean, default=True)
    telegram_chat_id = Column(String(50), nullable=True)

    # Verificacion de correo
    email_verified = Column(Boolean, default=False)
    email_verify_token = Column(String(64), nullable=True)

    # Suscripcion
    subscription_active = Column(Boolean, default=False)
    subscription_plan = Column(String(20), nullable=True)   # "trial","monthly","annual"
    subscription_expires_at = Column(DateTime, nullable=True)
    paypal_subscription_id = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
