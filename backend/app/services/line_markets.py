"""Mercados de linea (handicap y total) con el metodo sharp: regla sharp-v3 (20-oct-2026).

La referencia es la linea de Pinnacle (PICK_ANCHOR_BOOKMAKER) y su probabilidad sin margen
de que el local cubra (o de que salga over). Las casas blandas casi nunca comparten la linea
de Pinnacle (4-6 de 22 en NBA) y a linea igual pagan menos, asi que el valor esta en la
LINEA DESFASADA: una blanda que sigue en -5,5 cuando Pinnacle ya esta en -7.

Conversion entre lineas: el margen (local - visitante) y el total se tratan como normales
con desviacion fija por liga (LINE_SIGMA_*) y media implicada por la linea y el precio de
Pinnacle. Para cualquier otra linea se calcula la probabilidad de ganar y de empatar (push,
lineas enteras: corregido por continuidad, los puntos son enteros) y el EV del precio de
la blanda: edge = p_gana * cuota + p_push - 1. Sin margen de Pinnacle no hay pick.

Limites (config): distancia maxima entre la linea de la blanda y la de Pinnacle
(LINE_MAX_DIST_SPREAD / _TOTAL), edge minimo y maximo (los mismos que el ganador).

Convenciones (las de odds_fetcher / score_resolver):
  spread_line = handicap del LOCAL (negativo = favorito); el local cubre si margen + linea > 0.
  bet_type 'spread_home_-5.5' (linea del local) / 'spread_away_5.5' (linea del visitante = -linea local),
           'total_points_over_215.5' / 'total_points_under_215.5'. Push -> void (score_resolver).
"""
from __future__ import annotations

import math
from statistics import median
from typing import Optional

from app.config import settings

SHARP_BKS = set(settings.SHARP_BOOKMAKERS)
EXCHANGE_BKS = {"betfair_ex_eu", "betfair_ex_uk", "betfair_ex_au", "matchbook", "smarkets"}
EXCLUDED_SOFT = SHARP_BKS | EXCHANGE_BKS


def _phi(x: float) -> float:
    """Funcion de distribucion de la normal estandar."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phi_inv(p: float) -> float:
    """Inversa de la normal estandar (Acklam, error < 1e-9)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p fuera de (0,1)")
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def devig(odds_a, odds_b) -> Optional[float]:
    """Probabilidad sin margen del lado A (metodo proporcional, como value_calculator)."""
    if not odds_a or not odds_b or odds_a <= 1.0 or odds_b <= 1.0:
        return None
    ia, ib = 1.0 / odds_a, 1.0 / odds_b
    return ia / (ia + ib)


def sigma(liga: str, mercado: str) -> float:
    tabla = settings.LINE_SIGMA_SPREAD if mercado == "spread" else settings.LINE_SIGMA_TOTAL
    return float(tabla.get(liga or "", tabla.get("default")))


def media_implicada(umbral: float, p_mayor: float, sd: float) -> float:
    """Media de la normal tal que P(X > umbral) = p_mayor (umbral = -linea del local, o el total)."""
    return umbral + sd * _phi_inv(p_mayor)


def prob_gana_push(mu: float, sd: float, umbral: float) -> tuple[float, float]:
    """Para una apuesta que gana si X > umbral (X entero): (P gana, P push). Push solo con umbral entero."""
    if abs(umbral - round(umbral)) < 1e-9:
        t = round(umbral)
        p_gana = 1.0 - _phi((t + 0.5 - mu) / sd)
        p_push = _phi((t + 0.5 - mu) / sd) - _phi((t - 0.5 - mu) / sd)
    else:
        p_gana = 1.0 - _phi((math.floor(umbral) + 0.5 - mu) / sd)
        p_push = 0.0
    return p_gana, p_push


def edge_pct(p_gana: float, p_push: float, cuota: float) -> float:
    """EV en % de apostar 1 a esa cuota (el push devuelve la unidad)."""
    return (p_gana * cuota + p_push - 1.0) * 100.0


# ──────────────────────────────────────────────────────────────
# Referencia de Pinnacle y evaluacion de cada lado
# ──────────────────────────────────────────────────────────────

def referencia(odds_by_bk: dict, mercado: str, liga: str) -> Optional[dict]:
    """Linea y media implicada de la casa ancla (Pinnacle) para 'spread' o 'total'.

    spread: X = margen local - visitante; el local cubre si X > -linea.
    total:  X = total de puntos; over si X > linea.
    Devuelve {'linea', 'mu', 'sd', 'p_ref', 'cuota_a', 'cuota_b'} o None si Pinnacle no cotiza la linea.
    """
    anchor = odds_by_bk.get(settings.PICK_ANCHOR_BOOKMAKER) or {}
    if mercado == "spread":
        linea, ca, cb = anchor.get("spread_line"), anchor.get("odds_spread_home"), anchor.get("odds_spread_away")
    else:
        linea, ca, cb = anchor.get("total_line"), anchor.get("odds_over"), anchor.get("odds_under")
    if linea is None:
        return None
    p = devig(ca, cb)
    if not p or not (0.05 < p < 0.95):
        return None
    sd = sigma(liga, mercado)
    umbral = -float(linea) if mercado == "spread" else float(linea)
    # p es P(gana | no push) para la linea de Pinnacle; con linea entera la media exacta exige iterar:
    # una correccion de punto fijo de dos pasos basta (el push pesa ~3 %).
    mu = media_implicada(umbral, p, sd)
    for _ in range(2):
        pg, pp = prob_gana_push(mu, sd, umbral)
        if pg + pp >= 1.0 or pg <= 0:
            break
        objetivo = p * (1.0 - pp)                  # P(gana) = p * (1 - P(push))
        mu = media_implicada(umbral, objetivo, sd)
    return {"linea": float(linea), "mu": mu, "sd": sd, "p_ref": p, "cuota_a": ca, "cuota_b": cb}


def evaluar_lado(odds_by_bk: dict, mercado: str, lado: str, ref: dict) -> Optional[dict]:
    """Mejor pick del lado ('home'/'away' en spread, 'over'/'under' en total) entre las blandas.

    Para cada blanda con linea y precio del lado: probabilidad de ganar y de push a SU linea
    (normal de la referencia) y edge. Se elige la de mayor edge dentro de los limites.
    """
    if mercado == "spread":
        campo_linea, campo_cuota = "spread_line", ("odds_spread_home" if lado == "home" else "odds_spread_away")
        max_dist = settings.LINE_MAX_DIST_SPREAD
    else:
        campo_linea, campo_cuota = "total_line", ("odds_over" if lado == "over" else "odds_under")
        max_dist = settings.LINE_MAX_DIST_TOTAL
    mejor = None
    precios_misma_linea = []
    for bk, data in odds_by_bk.items():
        if bk in EXCLUDED_SOFT:
            continue
        linea, cuota = data.get(campo_linea), data.get(campo_cuota)
        if linea is None or not cuota or cuota <= 1.0:
            continue
        if cuota < settings.SYSTEM_MIN_ODDS or cuota > settings.SYSTEM_MAX_ODDS:
            continue
        if abs(float(linea) - ref["linea"]) > max_dist + 1e-9:
            continue
        p_gana, p_push = _prob_lado(ref, mercado, lado, float(linea))
        edge = edge_pct(p_gana, p_push, cuota)
        if abs(float(linea) - ref["linea"]) < 1e-9:
            precios_misma_linea.append(cuota)
        if edge < settings.SYSTEM_MIN_EDGE or edge > settings.SA_MAX_EDGE:
            continue
        if mejor is None or edge > mejor["edge"]:
            mejor = {"bk": bk, "cuota": cuota, "linea_soft": float(linea), "p_gana": p_gana, "p_push": p_push,
                     "edge": edge}
    if mejor is None:
        return None
    # Pinnacle a NUESTRA linea: probabilidad y cuota justa (con el push devuelto)
    pg_ref, pp_ref = _prob_lado(ref, mercado, lado, mejor["linea_soft"])
    mejor["pin_fair"] = round((1.0 - pp_ref) / pg_ref, 4) if pg_ref > 0 else None
    mejor["pin_raw"] = ref["cuota_a"] if lado in ("home", "over") else ref["cuota_b"]
    mejor["ref_linea"] = ref["linea"]
    mejor["median_misma_linea"] = round(float(median(precios_misma_linea)), 4) if precios_misma_linea else None
    mejor["n_misma_linea"] = len(precios_misma_linea)
    # linea de la apuesta en la convencion del bet_type
    if mercado == "spread":
        mejor["linea_apuesta"] = mejor["linea_soft"] if lado == "home" else -mejor["linea_soft"]
        mejor["bet_type"] = f"spread_{lado}_{_fmt(mejor['linea_apuesta'])}"
    else:
        mejor["linea_apuesta"] = mejor["linea_soft"]
        mejor["bet_type"] = f"total_points_{lado}_{_fmt(mejor['linea_apuesta'])}"
    mejor["priority"] = mejor["edge"] * mejor["p_gana"]
    return mejor


def _prob_lado(ref: dict, mercado: str, lado: str, linea: float) -> tuple[float, float]:
    """(P gana, P push) del lado a una linea dada, con la normal de la referencia."""
    mu, sd = ref["mu"], ref["sd"]
    if mercado == "spread":
        umbral = -linea                               # local cubre si X > -linea
        pg, pp = prob_gana_push(mu, sd, umbral)
        if lado == "home":
            return pg, pp
        return 1.0 - pg - pp, pp                      # visitante cubre si X < -linea
    pg, pp = prob_gana_push(mu, sd, linea)            # over si X > linea
    if lado == "over":
        return pg, pp
    return 1.0 - pg - pp, pp


def prob_lado_a_linea(ref: dict, mercado: str, lado: str, linea: float) -> tuple[float, float]:
    """Publico: (P gana, P push) de un lado a una linea con una referencia (para el CLV)."""
    return _prob_lado(ref, mercado, lado, linea)


def _fmt(x: float) -> str:
    """-5.5 -> '-5.5', 7.0 -> '7.0' (float siempre con decimal, parseable por score_resolver)."""
    return f"{x:.1f}"


def lado_y_linea(bet_type: str) -> Optional[tuple[str, str, float]]:
    """'spread_home_-5.5' -> ('spread','home',-5.5); 'total_points_over_215.5' -> ('total','over',215.5)."""
    try:
        if bet_type.startswith("spread_home_"):
            return "spread", "home", float(bet_type[len("spread_home_"):])
        if bet_type.startswith("spread_away_"):
            return "spread", "away", float(bet_type[len("spread_away_"):])
        if bet_type.startswith("total_points_over_"):
            return "total", "over", float(bet_type[len("total_points_over_"):])
        if bet_type.startswith("total_points_under_"):
            return "total", "under", float(bet_type[len("total_points_under_"):])
    except ValueError:
        return None
    return None
