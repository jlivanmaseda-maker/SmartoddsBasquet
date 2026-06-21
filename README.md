# SmartOdds Basketball 🏀

Plataforma de **value betting** para baloncesto (NBA, EuroLeague, NCAA, WNBA...),
portada de la arquitectura de **SmartOdds Tennis**.

> **Estado:** esqueleto. Infraestructura funcional; servicios pesados a portar.
> Ver [`CLAUDE.md`](CLAUDE.md) y [`SmartOdds_Basketball_Blueprint.md`](SmartOdds_Basketball_Blueprint.md).

## Estructura

```
backend/                 FastAPI + GraphQL + SQLAlchemy + APScheduler
  app/
    config.py            ligas, mercados, pesos, bookmakers (FUNCIONAL)
    main.py              entry FastAPI (FUNCIONAL, stubs opcionales)
    db/database.py       SQLite/PostgreSQL (FUNCIONAL)
    models/              Match, Team, Odds, Pick, UserBet, User (FUNCIONAL)
    services/            scheduler, odds_fetcher, value_calculator,
                         score_resolver, kelly, clv, notifications, auth (STUBS)
    ml/                  model (ensemble), elo_calculator, calibrator, SA (STUBS)
    schemas/             GraphQL (STUB)
frontend-react/          React 19 + TS + Vite (esqueleto + constantes)
deploy/                  systemd + nginx (VPS2 212.227.50.152, puerto 8002)
scripts/                 deploy.sh
```

## Arranque rapido (dev)

```bash
# backend
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env        # rellenar claves
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload

# frontend
cd ../frontend-react
npm install && npm run dev
```

Comprobar: http://127.0.0.1:8002/status

## Siguientes pasos

1. Conseguir clave/cobertura de The Odds API para basket y portar `odds_fetcher`.
2. Portar `value_calculator` + `score_resolver` + `scheduler` desde tenis.
3. Completar el ensemble (`ml/model.py`) y hacer backtest historico.
4. Calibrar `SYSTEM_MIN_EDGE` y pesos con Simulated Annealing.
5. Portar GraphQL + frontend.
