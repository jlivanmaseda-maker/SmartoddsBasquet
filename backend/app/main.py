"""SmartOdds Basketball - API Backend.

Plataforma de Value Betting con IA para baloncesto (NBA, EuroLeague, NCAA,
WNBA...). Adaptacion de SmartOdds Tennis al deporte de equipo.

Integra:
- FastAPI con lifespan (arranque/parada del scheduler)
- CORS middleware
- GraphQL via Strawberry en /graphql (cuando schemas/graphql_schema.py este listo)
- Endpoints REST para auth, status y admin

NOTA: este es el esqueleto. Los servicios (scheduler, auth) se cargan de forma
opcional con try/except para poder arrancar el backend aunque aun esten vacios.
"""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.config import settings
from app.logging_config import setup_logging
from app.db.database import init_db

setup_logging()

try:
    from app.services.scheduler import odds_scheduler
    HAS_SCHEDULER = True
except ImportError:
    HAS_SCHEDULER = False

try:
    from app.services.auth_service import auth_service
    HAS_AUTH = True
except ImportError:
    HAS_AUTH = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida: init DB + arrancar scheduler; parar al apagar."""
    init_db()
    if HAS_SCHEDULER:
        odds_scheduler.start()
    yield
    if HAS_SCHEDULER:
        odds_scheduler.stop()


app = FastAPI(
    title="SmartOdds Basketball",
    description="Value Betting Basketball Platform — NBA / EuroLeague / NCAA / WNBA",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GraphQL mount (se activa cuando graphql_schema.py este listo)
try:
    from app.schemas.graphql_schema import schema
    from strawberry.fastapi import GraphQLRouter

    graphql_app = GraphQLRouter(schema)
    app.include_router(graphql_app, prefix="/graphql")
except ImportError:
    pass


@app.get("/status")
async def status():
    """Health check + estado de servicios."""
    result = {
        "status": "ok",
        "sport": settings.SPORT,
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if HAS_SCHEDULER:
        result["scheduler"] = odds_scheduler.get_service_status()
    return result


@app.get("/api/status/config")
async def status_config():
    """Configuracion del sistema: ligas, mercados, intervalos."""
    return {
        "sport": settings.SPORT,
        "monitored_leagues": settings.MONITORED_LEAGUES,
        "all_leagues": settings.ALL_LEAGUES,
        "shadow_leagues": list(settings.SHADOW_LEAGUES),
        "active_markets": settings.ACTIVE_MARKETS,
        "shadow_markets": list(settings.SHADOW_MARKETS),
        "odds_update_interval_minutes": settings.ODDS_UPDATE_INTERVAL_MINUTES,
        "scores_update_interval_minutes": settings.SCORES_UPDATE_INTERVAL_MINUTES,
        "system_min_edge": settings.SYSTEM_MIN_EDGE,
        "system_min_odds": settings.SYSTEM_MIN_ODDS,
        "system_max_odds": settings.SYSTEM_MAX_ODDS,
        "kelly_fraction": settings.KELLY_FRACTION,
        "bookmakers": settings.BOOKMAKERS,
        "sharp_bookmakers": settings.SHARP_BOOKMAKERS,
    }


# TODO: portar de tenis los endpoints REST de auth (/auth/*), admin
# (/api/admin/*) y PayPal (/api/paypal/*) cuando los servicios esten listos.


# Serve React frontend (static files) en produccion
frontend_dist = Path(__file__).parent.parent.parent / "frontend-react" / "dist"
if frontend_dist.exists() and (frontend_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    _dist_root = frontend_dist.resolve()

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Guard anti path-traversal: solo se sirven ficheros DENTRO de dist/
        # (nginx ya rechaza '..' con 400, pero el backend no debe depender de eso).
        file_path = (frontend_dist / full_path).resolve()
        if file_path.is_file() and _dist_root in file_path.parents:
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))
