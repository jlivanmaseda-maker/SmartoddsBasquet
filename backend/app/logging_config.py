"""Configuracion de logging estructurado (consola + fichero)."""
import logging
import os
import sys

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "logs")


def setup_logging():
    """Inicializa el logger raiz del proyecto."""
    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(os.path.join(LOG_DIR, "app.log")))
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
