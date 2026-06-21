"""Servicio de autenticacion (JWT + bcrypt). Identico a tenis.

ESQUELETO funcional minimo. Portar el resto de tenis (services/auth_service.py).
"""
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.config import settings
from app.db.database import SessionLocal
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain: str, hashed: str) -> bool:
        return pwd_context.verify(plain, hashed)

    def create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def decode_token(self, token: str) -> dict:
        try:
            return jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
        except Exception:
            return None

    def authenticate_user(self, username: str, password: str):
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            if not user or not self.verify_password(password, user.hashed_password):
                return None
            return user
        finally:
            db.close()


auth_service = AuthService()
