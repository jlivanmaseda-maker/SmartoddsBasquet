"""Configuracion de logging estructurado (consola + fichero)."""
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "logs")

# Parametros y rutas con secretos: la clave de The Odds API y el token de BetsAPI van en la URL, y el de Telegram
# en la ruta (/bot<token>/).
_SECRETOS = (
    (re.compile(r"(?i)\b(apikey|api_key|token)=[^&\s'\"]+"), r"\1=***"),
    (re.compile(r"/bot\d+:[\w-]+"), "/bot***"),
)


def redactar(texto: str) -> str:
    """Quita claves y tokens de un texto."""
    for patron, cambio in _SECRETOS:
        texto = patron.sub(cambio, texto)
    return texto


class FiltroSecretos(logging.Filter):
    """Red de seguridad: quita secretos del mensaje y de la traza de cualquier linea (un error de httpx lleva la URL)."""

    def filter(self, record: logging.LogRecord) -> bool:
        mensaje = record.getMessage()
        limpio = redactar(mensaje)
        if limpio != mensaje:
            record.msg, record.args = limpio, ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redactar(record.exc_text)
        return True


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

    filtro = FiltroSecretos()
    for h in handlers:
        h.addFilter(filtro)

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=fmt,
        handlers=handlers,
    )
    # httpx escribe a INFO la URL completa de cada peticion, con la clave dentro (31-oct-2026)
    for ruidoso in ("httpx", "httpcore"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    logging.getLogger("smartodds_basketball").setLevel(
        getattr(logging, LOG_LEVEL, logging.INFO)
    )
