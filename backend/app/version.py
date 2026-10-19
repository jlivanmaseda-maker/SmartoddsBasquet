"""Version desplegada (fichero VERSION en la raiz de la app) y version de regla.

- APP_VERSION: contenido de VERSION (commit corto + fecha), "dev" si no existe.
- RULE_VERSION: etiqueta de la regla que crea los picks. Cada regla se mide por
  separado y desde su hora de despliegue (metodo TT). Cambiarla SOLO cuando
  cambie algo que afecte a que picks salen o a que cuota (umbrales, ventana,
  casas, mercados): asi los picks viejos y los nuevos no se mezclan.
"""
import os
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def _read_version() -> str:
    try:
        v = _VERSION_FILE.read_text(encoding="utf-8").strip()
        if v:
            return v
    except OSError:
        pass
    return os.getenv("APP_VERSION", "dev")


APP_VERSION: str = _read_version()

# sharp-v1: regla original (21-jun-2026): devig sharp, edge 3-12, cuota 1.20-5.00,
#           ventana 24 h y espera a Pinnacle desde el 5-sep-2026.
# sharp-v2: misma regla y mismos umbrales, pero el pick guarda la mediana de
#           las blandas, Pinnacle y la version (19-oct-2026), y se capturan
#           spreads y totales.
RULE_VERSION: str = os.getenv("RULE_VERSION", "sharp-v2")

# sharp-v3: picks de handicap y total (20-oct-2026), linea de Pinnacle convertida a la
#           linea de cada blanda con una normal por liga. Se mide aparte del ganador.
RULE_VERSION_LINES: str = os.getenv("RULE_VERSION_LINES", "sharp-v3")
