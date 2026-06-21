"""Conexion a base de datos con SQLAlchemy.

Soporta SQLite (desarrollo) y PostgreSQL (produccion).
Identico al patron de SmartOdds Tennis.
"""
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if is_sqlite:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-8000")
        cursor.close()
else:
    engine = create_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=20,
        max_overflow=40,
        pool_timeout=60,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency para obtener sesion de DB."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_migrations(eng, sqlite: bool):
    """Migraciones incrementales: agrega columnas nuevas a tablas existentes.

    TODO: ir anadiendo aqui columnas a medida que evolucione el esquema,
    igual que en tenis (no usamos Alembic pese a estar en requirements).
    """
    new_columns = [
        # (tabla, columna, tipo_pg, tipo_sqlite)
        ("matches", "elo_applied", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
    ]

    if not new_columns:
        return

    try:
        with eng.connect() as conn:
            for table, col, pg_type, sq_type in new_columns:
                try:
                    if sqlite:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN {col} {sq_type}"
                        ))
                    else:
                        conn.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {pg_type}"
                        ))
                except Exception:
                    pass
            conn.commit()
    except Exception as e:
        print(f"[DB] Warning: Migration error (safe to ignore): {e}")


def init_db():
    """Crear todas las tablas."""
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _run_migrations(engine, is_sqlite)

    if not is_sqlite:
        try:
            with engine.connect() as conn:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_picks_active "
                    "ON picks (created_at DESC) WHERE is_active = true"
                ))
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_odds_match_bookmaker "
                    "ON odds (match_id, bookmaker)"
                ))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_teams_name "
                    "ON teams (name)"
                ))
                conn.commit()
                print("[DB] Indices PostgreSQL creados/verificados")
        except Exception as e:
            print(f"[DB] Warning: No se pudieron crear indices adicionales: {e}")
