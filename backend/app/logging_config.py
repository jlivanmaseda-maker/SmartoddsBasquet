"""Configuracion de logging estructurado (consola + fichero)."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "logs")


def setup_logging():
    """Inicializa el logger raiz del proyecto."""
    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        # Rotacion: 10 MB x 5 ficheros (journald ya guarda la salida completa).
        handlers.append(RotatingFileHandler(
            os.path.join(LOG_DIR, "app.log"),
            maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
        ))
    except Exception:
        pass

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=fmt,
        handlers=handlers,
    )
    logging.getLogger("smartodds_basketball").setLevel(
        getattr(logging, LOG_LEVEL, logging.INFO)
    )
