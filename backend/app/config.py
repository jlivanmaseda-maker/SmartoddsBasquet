"""Configuracion global de SmartOdds Basketball.

Adaptado de SmartOdds Tennis. La arquitectura core (fetch odds -> modelo ->
edge/Kelly -> resolucion -> ELO) es identica; cambia el modelo de datos
(equipos en vez de jugadores) y los mercados (puntos en vez de games/sets).
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Database (SQLite por defecto para desarrollo local, PostgreSQL para produccion)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///smartodds_basketball.db"
    )

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "43200")  # 30 days
    )

    # The Odds API (misma API/clave que tenis y futbol, cubre basket)
    ODDS_API_KEY: str = os.getenv("ODDS_API_KEY", "")
    ODDS_API_BASE_URL: str = "https://api.the-odds-api.com/v4"

    # Basketball Scores API (API-Basketball o similar — TODO confirmar proveedor)
    BASKETBALL_SCORES_API_KEY: str = os.getenv("BASKETBALL_SCORES_API_KEY", "")
    BASKETBALL_SCORES_API_BASE_URL: str = os.getenv(
        "BASKETBALL_SCORES_API_BASE_URL",
        "https://api.api-basketball.com/"
    )

    # BetsAPI (scores/results + ligas FUERA de The Odds API)
    # Volume One plan compartido con tenis/table tennis (199,999 req/hour)
    BETSAPI_TOKEN: str = os.getenv("BETSAPI_TOKEN", "")
    BETSAPI_ODDS_INTERVAL_MINUTES: int = int(
        os.getenv("BETSAPI_ODDS_INTERVAL_MINUTES", "5")
    )
    # sport_id de basket en BetsAPI (tennis=13, table tennis=92, basketball=18)
    BETSAPI_BASKETBALL_SPORT_ID: int = int(os.getenv("BETSAPI_BASKETBALL_SPORT_ID", "18"))
    # Activar la ingesta de odds via BetsAPI (ligas no cubiertas por The Odds API)
    BETSAPI_ODDS_ENABLED: bool = os.getenv("BETSAPI_ODDS_ENABLED", "true").lower() == "true"
    # Substrings de nombre de liga a INCLUIR (BetsAPI no usa nuestros sport_keys).
    # Empezamos por ACB (Espana); ampliar con LNB, BBL, Lega A, etc.
    BETSAPI_LEAGUES: list = os.getenv("BETSAPI_LEAGUES", "ACB,Spain").split(",")
    # Mapeo substring de liga -> league_tier interno (para el modelo/filtros)
    BETSAPI_LEAGUE_TIER_MAP: dict = {
        "acb": "acb",
        "spain": "acb",
        "lnb": "lnb",
        "france": "lnb",
        "lega": "lega_a",
        "italy": "lega_a",
        "bbl": "bbl",
        "germany": "bbl",
    }

    # BetBurger (valuebet comparison tracker — odds via VPS XL centralizado)
    BETBURGER_API_TOKEN: str = os.getenv("BETBURGER_API_TOKEN", "")
    BETBURGER_FILTER_ID: str = os.getenv("BETBURGER_FILTER_ID", "")
    BETBURGER_INGEST_SECRET: str = os.getenv("BETBURGER_INGEST_SECRET", "")

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # ================================================================
    # EMAIL (Resend) — verificacion de correo + bienvenida
    # ================================================================
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "SmartOdds Basket <noreply@smartoddsbasket.es>")
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://smartoddsbasket.es")
    DISCORD_INVITE_URL: str = os.getenv("DISCORD_INVITE_URL", "")

    # ================================================================
    # PAYPAL (pasarela de suscripciones) — identico a tenis
    # ================================================================
    PAYPAL_CLIENT_ID: str = os.getenv("PAYPAL_CLIENT_ID", "")
    PAYPAL_CLIENT_SECRET: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    PAYPAL_MODE: str = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox | live
    PAYPAL_WEBHOOK_ID: str = os.getenv("PAYPAL_WEBHOOK_ID", "")
    PAYPAL_PLAN_ID_MONTHLY: str = os.getenv("PAYPAL_PLAN_ID_MONTHLY", "")
    PAYPAL_PLAN_ID_ANNUAL: str = os.getenv("PAYPAL_PLAN_ID_ANNUAL", "")
    PAYPAL_CURRENCY: str = os.getenv("PAYPAL_CURRENCY", "EUR")
    PAYPAL_PRICE_MONTHLY: str = os.getenv("PAYPAL_PRICE_MONTHLY", "49.99")
    PAYPAL_PRICE_ANNUAL: str = os.getenv("PAYPAL_PRICE_ANNUAL", "499")

    # Free trial sin tarjeta al registrarse (0 = desactivado)
    TRIAL_DAYS: int = int(os.getenv("TRIAL_DAYS", "14"))

    # Intervalos de scraping
    ODDS_UPDATE_INTERVAL_MINUTES: int = int(
        os.getenv("ODDS_UPDATE_INTERVAL_MINUTES", "15")
    )
    SCORES_UPDATE_INTERVAL_MINUTES: int = int(
        os.getenv("SCORES_UPDATE_INTERVAL_MINUTES", "5")
    )

    SPORT: str = "basketball"

    # ================================================================
    # LIGAS MONITORIZADAS — The Odds API sport_keys para basket
    # ================================================================
    # Empezamos amplio (todas) y filtramos por rentabilidad mas adelante.
    MONITORED_LEAGUES: list = os.getenv(
        "MONITORED_LEAGUES",
        "basketball_nba,basketball_euroleague,basketball_ncaab,basketball_wnba,"
        "basketball_nba_summer_league"
    ).split(",")

    # Todas las ligas de basket disponibles en The Odds API
    ALL_LEAGUES: list = [
        "basketball_nba",
        "basketball_nba_preseason",
        "basketball_nba_summer_league",  # Las Vegas Summer League (verano)
        "basketball_wnba",
        "basketball_ncaab",            # NCAA College Basketball (mucho volumen)
        "basketball_ncaab_championship_winner",
        "basketball_euroleague",
        "basketball_nbl",              # Australia
    ]
    # Ligas adicionales no siempre presentes en The Odds API (via BetsAPI):
    #   ACB (Espana), Lega A (Italia), LNB (Francia), BBL (Alemania), etc.

    # Ligas shadow: generan picks con is_shadow=True para evaluar rendimiento
    SHADOW_LEAGUES: set = set()

    # Tiers shadow: picks en estos tiers son shadow (sin alertas Telegram, sin
    # apostar). FASE DE CALIBRACION: TODAS las ligas en shadow hasta que
    # scripts/backtest_shadow.py confirme rentabilidad con datos acumulados.
    # Para promover una liga a ACTIVE: quitarla de este set tras validarla.
    SHADOW_TIERS: set = {"nba", "nba_sl", "wnba", "ncaab", "euroleague", "nbl"}

    # ================================================================
    # MERCADOS DE BASKET
    # ================================================================
    # Mercado principal desde dia 1 (2 vias, sin empate — como en tenis)
    ACTIVE_MARKETS: list = [
        "match_winner",          # Ganador del partido (h2h / moneyline)
    ]

    # Mercados shadow (trackear sin mostrar hasta tener datos)
    SHADOW_MARKETS: set = {
        "spread_home",           # Hándicap de puntos local
        "spread_away",           # Hándicap de puntos visitante
        "total_points_over",     # Over X.5 puntos
        "total_points_under",    # Under X.5 puntos
    }

    # ================================================================
    # MODELO — Ensemble de basket (pesos placeholder, optimizar con SA)
    # ================================================================
    # Componentes adaptados de tenis al deporte de equipo. TODO: re-optimizar
    # via simulated_annealing sobre backtest historico una vez haya datos.
    ELO_TEAM_WEIGHT: float = float(os.getenv("ELO_TEAM_WEIGHT", "0.40"))
    NET_RATING_WEIGHT: float = float(os.getenv("NET_RATING_WEIGHT", "0.25"))
    FORM_WEIGHT: float = float(os.getenv("FORM_WEIGHT", "0.15"))
    REST_WEIGHT: float = float(os.getenv("REST_WEIGHT", "0.10"))   # back-to-back / dias descanso
    HOME_COURT_WEIGHT: float = float(os.getenv("HOME_COURT_WEIGHT", "0.05"))
    H2H_WEIGHT: float = float(os.getenv("H2H_WEIGHT", "0.05"))

    # ================================================================
    # EDGE Y FILTROS
    # SA_MAX_EDGE=12: backtest shadow 28-Jul-2026 (147 picks) — edge 12%+
    # pierde (-7% ROI, n=32); buckets 3-12% todos rentables.
    # ================================================================
    SYSTEM_MIN_EDGE: float = float(os.getenv("SYSTEM_MIN_EDGE", "3.0"))
    SYSTEM_MAX_ODDS: float = float(os.getenv("SYSTEM_MAX_ODDS", "5.0"))
    SYSTEM_MIN_ODDS: float = float(os.getenv("SYSTEM_MIN_ODDS", "1.20"))
    SA_MAX_EDGE: float = float(os.getenv("SA_MAX_EDGE", "12.0"))
    DISPLAY_MAX_EDGE: float = float(os.getenv("DISPLAY_MAX_EDGE", "15.0"))

    # ================================================================
    # SIMULATED ANNEALING (recalibracion semanal de pesos)
    # ================================================================
    SA_MAX_ITERATIONS: int = int(os.getenv("SA_MAX_ITERATIONS", "5000"))
    SA_COOLING_RATE: float = float(os.getenv("SA_COOLING_RATE", "0.97"))
    SA_INITIAL_TEMP: float = float(os.getenv("SA_INITIAL_TEMP", "1.0"))
    SA_MIN_TEMP: float = float(os.getenv("SA_MIN_TEMP", "0.001"))
    SA_PERTURBATION_SCALE: float = float(os.getenv("SA_PERTURBATION_SCALE", "0.05"))
    SA_OBJECTIVE: str = os.getenv("SA_OBJECTIVE", "combined")
    SA_MIN_PICKS: int = int(os.getenv("SA_MIN_PICKS", "50"))

    # ================================================================
    # LIGHTGBM FALLBACK (non-Pinnacle tiers)
    # ================================================================
    LGBM_ENABLED: bool = os.getenv("LGBM_ENABLED", "true").lower() == "true"
    LGBM_MIN_TRAINING_SAMPLES: int = int(os.getenv("LGBM_MIN_TRAINING_SAMPLES", "200"))
    LGBM_BLEND_ALPHA: float = float(os.getenv("LGBM_BLEND_ALPHA", "0.60"))

    # ================================================================
    # STAKING KELLY CRITERION (identico a tenis/futbol)
    # ================================================================
    KELLY_FRACTION: float = float(os.getenv("KELLY_FRACTION", "0.25"))
    KELLY_MIN_PROFIT_PCT: float = float(os.getenv("KELLY_MIN_PROFIT_PCT", "0.01"))
    KELLY_MAX_PROFIT_PCT: float = float(os.getenv("KELLY_MAX_PROFIT_PCT", "0.04"))
    KELLY_MAX_STAKE_PCT: float = float(os.getenv("KELLY_MAX_STAKE_PCT", "0.05"))

    # App
    DEFAULT_BANKROLL: float = float(os.getenv("DEFAULT_BANKROLL", "1000"))
    DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "EUR")

    # Stats update schedule
    STATS_UPDATE_HOUR: int = int(os.getenv("STATS_UPDATE_HOUR", "6"))

    # The Odds API regions (us para NBA/NCAA, eu para Euroliga/ACB)
    ODDS_API_REGIONS: str = os.getenv("ODDS_API_REGIONS", "us,eu,uk")
    # Solo h2h para picks activos; spreads/totals son shadow -> reduce coste.
    ODDS_API_MARKETS: str = os.getenv("ODDS_API_MARKETS", "h2h")

    # ================================================================
    # BOOKMAKERS — conjunto SHARP ESPECÍFICO DE BASKET (no el de tenis)
    # ================================================================
    # Investigado 21-Jun-2026 sobre los datos reales de The Odds API + fuentes:
    # en basket USA las casas sharp presentes son Pinnacle, BetOnline (~3.18%
    # juice, top NBA), LowVig.ag (reduced juice) y 1xBet. Circa marca mercado
    # pero NO está en The Odds API. Estas son las que usamos para el devig
    # avg-line y el composite. El "océano soft" = casas recreativas USA
    # (FanDuel, DraftKings, BetMGM, ESPN Bet, Fanatics, Bovada...) donde aparece
    # el valor. (En tenis el set sharp era solo {pinnacle, onexbet}.)
    SHARP_BOOKMAKERS: list = ["pinnacle", "betonlineag", "lowvig", "onexbet"]
    SHARP_FALLBACK_BOOKMAKERS: list = ["betanysports", "mybookieag", "betus"]

    SOFT_BOOKMAKERS: list = [
        "winamax_fr", "williamhill", "bet365", "unibet_eu",
        "betsson", "coolbet", "nordicbet", "bwin",
        "betway", "sport888", "betano",
        "draftkings", "fanduel", "betmgm",
    ]

    BOOKMAKER_DISPLAY_NAMES: dict = {
        "bet365": "Bet365",
        "bwin": "Bwin",
        "betway": "Betway",
        "pinnacle": "Pinnacle",
        "sport888": "888sport",
        "williamhill": "William Hill",
        "onexbet": "1xBet",
        "winamax_fr": "Winamax",
        "betano": "Betano",
        "draftkings": "DraftKings",
        "fanduel": "FanDuel",
        "betmgm": "BetMGM",
        "pointsbetus": "PointsBet",
        "betrivers": "BetRivers",
        "fonbet": "FonBet",
    }

    BOOKMAKERS: list = [
        "bet365", "bwin", "betway", "pinnacle", "sport888",
        "williamhill", "onexbet", "winamax_fr",
        "betsson", "nordicbet", "coolbet", "betano",
        # US bookmakers (NBA/NCAA via region us)
        "draftkings", "fanduel", "betmgm", "pointsbetus", "betrivers",
        # BetsAPI-only
        "fonbet",
    ]

    DEFAULT_BOOKMAKERS: list = [
        "bet365", "bwin", "betway", "winamax_fr", "sport888",
        "williamhill", "pinnacle", "betano",
    ]

    # ================================================================
    # ELO SEED — datasets historicos de partidos
    # ================================================================
    ELO_SEED_YEARS: int = int(os.getenv("ELO_SEED_YEARS", "5"))
    ELO_INITIAL_RATING: float = 1500.0
    ELO_K_FACTOR_DEFAULT: int = 20

    # K-factor por liga. Calibrado con backtest walk-forward sobre la temporada
    # NBA 2025-26 (1.326 partidos): mejor logloss en K~12-20 (con multiplicador
    # MOV el K efectivo es ~2.4x). Claves por league_tier (no por sport_key).
    ELO_K_FACTOR_BY_LEAGUE: dict = {
        "nba": 16,
        "euroleague": 16,
        "ncaab": 12,           # mucho ruido, K mas bajo
        "wnba": 16,
    }

    # Ventaja de cancha en puntos ELO. Backtest NBA 2025-26: el optimo cae en
    # 40-70 (no 100 — la ventaja de local en basket moderno es ~55-57%).
    ELO_HOME_ADVANTAGE: float = float(os.getenv("ELO_HOME_ADVANTAGE", "55.0"))


settings = Settings()
