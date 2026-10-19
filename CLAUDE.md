# CLAUDE.md

Guía para Claude Code (claude.ai/code) al trabajar en este repositorio.

## ⚠️ Aislamiento de proyectos

SmartOdds Básquet es un proyecto **independiente**. NUNCA mezclar datos, modelos,
filtros, claves ni código con tenis, table tennis o fútbol. Cada deporte es su
propio proyecto aislado. (Comparten infraestructura: misma VPS y mismas claves de
data-API, pero el código y los datos son separados.)

## Idioma

Hablar SIEMPRE en español con el usuario. Código, comentarios y nombres de
variables en inglés.

## Visión

Plataforma de **value betting** para baloncesto (WNBA, NBA, EuroLeague, NCAA).
Portada de la arquitectura de **SmartOdds Tennis** (el proyecto que mejor funciona).
Detecta apuestas de valor comparando la probabilidad "justa" del mercado sharp
contra las cuotas de las casas blandas.

## Estado (21-Jun-2026): COMPLETO Y EN PRODUCCIÓN (fase SHADOW)

URL pública: **https://smartbasquet.masedamultiservicios.es**
El sistema corre solo en la VPS, captando odds, generando picks en shadow,
resolviendo resultados y actualizando ELO. NO apuesta hasta calibrar (ver abajo).

## El método que tiene valor: SHARP DEVIG (no el modelo)

⭐ La señal primaria NO es el modelo ELO — es el **consenso de casas sharp**, igual
que en tenis. El modelo ELO es solo FALLBACK cuando no hay sharp.

`value_calculator.generate_picks()` para cada lado (home/away) de un partido:
1. **Devig de cada casa sharp**: quita el margen (método proporcional: implied de
   un lado / (implied lado + implied contrario)) y promedia → probabilidad "justa".
   `fair_odds = 1 / avg_sharp_prob`.
2. **best_soft** = mejor cuota entre casas blandas (excluye sharps y exchanges).
3. **edge = (sharp_prob − implied_best_soft) / implied_best_soft × 100**.
4. **Filtro mixed-line**: si la sharp es >3× la mediana soft → línea corrupta, fuera.
5. **BookDif** = (best_soft − sharp_composite)/sharp_composite × 100 (señal extra).
6. Sin sharp → fallback al modelo ELO y el pick va a SHADOW.

### ⭐ Casas sharp ESPECÍFICAS DE BÁSQUET (≠ tenis)

Verificado con datos reales de The Odds API + investigación (21-Jun-2026). En
básquet USA las sharp son distintas a tenis:

`SHARP_BOOKMAKERS = ["pinnacle", "betonlineag", "lowvig", "onexbet"]`

- **Pinnacle** — sharp global, bajo margen, no limita.
- **BetOnline** (`betonlineag`) — top sharp NBA, juice ~3,18%.
- **LowVig.ag** (`lowvig`) — reduced juice (hermana de BetOnline).
- **1xBet** (`onexbet`) — sharp, presente.
- **Circa** marca mercado pero NO está en The Odds API (no usable).

(En tenis el set sharp era solo `{pinnacle, onexbet}`.) El "océano soft" donde
aparece el valor = casas recreativas USA: FanDuel, DraftKings, BetMGM, ESPN Bet,
Fanatics, Bovada…

## Diferencias clave vs Tenis

| Tenis | Básquet |
|-------|---------|
| Player (jugador) | Team (equipo) |
| Superficie (hard/clay/grass) | Liga + ventaja de cancha |
| ELO por superficie | ELO equipo + ELO local/visitante |
| Sets / games | Puntos / cuartos / prórroga |
| Retirada/walkover = void | Aplazado/cancelado = void; prórroga = parte del resultado |
| Sharps: pinnacle, 1xbet | Sharps: pinnacle, betonline, lowvig, 1xbet |
| Mercados: ML, O/U games, hcap games | Mercados: ML (2 vías), spread puntos, O/U puntos |

## Arquitectura

**Monorepo:** `backend/` (Python FastAPI) + `frontend-react/` (React 19 + TS + Vite).
**API:** GraphQL (Strawberry) en `/graphql`. **DB:** SQLAlchemy — SQLite en la VPS.
**Scheduler:** APScheduler — odds cada 15 min, scores cada 5 min.

### Ciclo del scheduler (`services/scheduler.py`)
```
ODDS  (15 min): odds_fetcher.fetch_all() [The Odds API] + betsapi (off)
                -> Match + Team + Odds; luego value_calculator.generate_picks()
SCORES (5 min): score_resolver.resolve_completed() [The Odds API /scores]
                -> liquida picks (won/lost/void); luego update de ELO de equipo
```

### Componentes (todos funcionales salvo nota)
| Módulo | Función |
|--------|---------|
| `services/odds_fetcher.py` | The Odds API. Filtra ligas activas con `/sports` (gratis). |
| `services/value_calculator.py` | ⭐ Método sharp devig (primario) + modelo (fallback). |
| `services/bookdif_calculator.py` | Señal BookDif (sharp vs soft). |
| `services/clv_calculator.py` | ⭐ CLV vs cierre Pinnacle SIN margen (último snapshot de `odds_history` pre-tipoff). Se calcula al liquidar. |
| `services/score_resolver.py` | Resultados vía The Odds API `/scores`. BetsAPI = fallback. |
| `services/scheduler.py` | Orquesta los ciclos. |
| `services/notification_service.py` | Telegram (bot propio de básquet). |
| `services/betsapi_odds_fetcher.py` | ⏸️ Listo pero DESACTIVADO (sin cobertura, ver abajo). |
| `ml/model.py` | Ensemble (ELO+net rating+form+rest+home court), robusto a None. |
| `ml/elo_calculator.py` | Update de ELO de equipo (K por liga, ventaja de cancha). |
| `ml/elo_seed.py` | Crawler ESPN (sin API key) + backtest walk-forward + grid search. |
| `schemas/graphql_schema.py` | Queries: activePicks, resolvedPicks, stats, standings, systemConfig. |
| `scripts/backtest_shadow.py` | Calibrador: ROI + CLV por edge / cuota / liga / liga-mes. |
| `scripts/backfill_clv.py` | Rellena CLV de picks ya resueltos (dry-run por defecto, `--apply`). |
| `scripts/analyze_sharp_vs_pinnacle.py` | Diagnóstico (solo lectura): edge vs Pinnacle solo, movimiento de línea pick→cierre, sesgo de cada sharp. |
| `scripts/void_opening_line_picks.py` | Anula picks pendientes a >PICK_MAX_HOURS_AHEAD (dry-run, `--apply`). |
| `scripts/vigilante.py` / `.sh` | ⭐ Vigilante cada 10 min + `--resumen` diario con canario (19-oct-2026). Avisa por Telegram al cambiar. |
| `scripts/fix_nba_teams.py` | Reenlaza partidos NBA a equipos `nba` (antes apuntaban a Summer League). Dry-run, `--apply`. |
| `scripts/backfill_median.py` | Reconstruye mediana de blandas y Pinnacle al crear el pick para los picks viejos. Dry-run, `--apply`. |
| `scripts/test_paso1.py` | Pruebas sin pytest de lo anterior (`cd backend && venv/bin/python ../scripts/test_paso1.py`). |

### Frontend (`frontend-react/`)
React 19 + TypeScript + Vite + **TailwindCSS v4 + Recharts + react-router**. Look
de tenis (tema oscuro navy `#0a0e17` + dorado, nav, tarjetas, gráficos). Sin
Apollo (fetch plano + hook `useQuery`). Sin auth/login/paypal. Páginas: Dashboard,
Picks, Tracking, Standings. El backend sirve el `dist` en `:8002`.

## Modelo / Calibración

- **Ensemble** (`ml/model.py`): ELO Team (0.40) + Net Rating (0.25) + Form (0.15)
  + Rest/back-to-back (0.10) + Home Court (0.05) + H2H (0.05). Es FALLBACK del sharp.
- **ELO seed + backtest** (`ml/elo_seed.py`): crawl de resultados de ESPN. Backtest
  NBA 2025-26 (1326 partidos): **67% de acierto**. Calibró `ELO_HOME_ADVANTAGE=55`
  (no 100 — la ventaja de local en basket moderno es ~55-57%) y K-factors por liga.
  WNBA 2026 ya seedeada a producción.
- **Pendiente (go-live)**: la calibración de `SYSTEM_MIN_EDGE` y qué ligas salen de
  shadow necesita histórico de picks resueltos CON CLV bajo el régimen de 24h /
  Pinnacle (desde 5-Sep-2026). `scripts/backtest_shadow.py` → decidir. La WNBA
  (137 picks, ROI +8% pero CLV −0,9%) NO se promueve hasta ver CLV > 0; si se
  promueve, con edge ≥5% y cuota <3,0 (los cortes que aguantaron jul-ago).

## ⭐ CLV y timing del pick (hallazgo 5-Sep-2026)

El CLV (cuota cogida vs cierre Pinnacle sin margen) es el indicador que manda,
no el ROI: con 217 picks el ROI era +6% pero el CLV medio −1,7% (45% positivos).
Todo el beneficio venía de junio (varianza). Causa: **timing**, no edge.
Pinnacle publica la WNBA ~23h antes del tipoff y los picks se creaban de media
37h antes (73% sin Pinnacle). Por antelación: 48-72h CLV −7,6%; 24-48h −1,3%;
12-24h **+4,1%** (68% positivos). Por eso:

- `PICK_MAX_HOURS_AHEAD=24` (antes 72).
- `PICK_ANCHOR_BOOKMAKER=pinnacle` + `PICK_WAIT_FOR_ANCHOR_HOURS=12`: no se crea
  NINGÚN pick sin Pinnacle cotizando hasta 12h antes del tipoff (el guard de
  conflicto haría que un pick temprano bloquease el maduro).
- Para promover una liga hay que ver CLV medio > 0 con este régimen, no solo ROI.
- `odds` (upsert) recibe cuotas EN VIVO tras el tipoff: el cierre se saca de
  `odds_history` (que solo guarda snapshot cuando la línea cambia).

## 19-oct-2026: paso 1 del traspaso TT (sharp-v2) — sombra medible

Inventario (sesión local SmartOddsBasquet, `inventario_2026-10-19.md`): 292 picks en
sombra desde el 21-jun; el ROI a cuota cogida (+6,6 %) es el mismo que a la cuota justa
de cierre (suerte, no ventaja); a mediana de las blandas +0,8 % ± 14; el ELO no aporta
sobre el cierre de Pinnacle (z +0,65). Cambios (la regla de los picks NO cambia):

- `rule_version` en cada pick (`sharp-v1` los viejos, `sharp-v2` desde este despliegue).
  Cada regla se mide por separado y desde su hora de despliegue. Umbral para publicar:
  ≥ 300 picks y ROI a mediana − 2 × error > 0 (`backtest_shadow.py`, sección por regla).
- `median_soft_odds`, `n_soft_books`, `pinnacle_odds_at_pick`, `pinnacle_fair_at_pick`
  en el pick; `scripts/backfill_median.py` los reconstruye para los viejos.
- Equipos por nombre Y liga en `_find_or_create_team`; `scripts/fix_nba_teams.py`
  reenlaza los 47 partidos de NBA que apuntaban a equipos de Summer League.
- Se piden h2h + spreads + totals (`ODDS_API_MARKETS`; el `.env` de la VPS manda): 9
  créditos por liga y llamada en vez de 3. Los picks siguen siendo solo de ganador.
- `scripts/vigilante.sh` en cron cada 10 min y `--resumen` diario (09:07 UTC): canario
  con entradas fijas (`scripts/canario_esperado.json`; regenerar con `--canario-generar`
  SOLO si se cambia el cálculo a propósito), `quick_check` y resumen por regla. Estado en
  `logs/vigilante_estado.json`.
- `VERSION` en la raíz de la app (no versionado): `<commit corto> <fecha>`; `/status` lo
  devuelve y el vigilante lo compara. `app/version.py` también fija `RULE_VERSION`.
- El cupo de The Odds API sale a INFO una vez por ciclo (`creditos: restantes=`).

## Disciplina SHADOW (mientras se calibra)

TODAS las ligas en `SHADOW_TIERS = {nba, wnba, ncaab, euroleague, nbl}`. Los picks
se registran para el backtest pero NO se emiten señales (sin Telegram, sin apostar).
Para promover una liga a ACTIVE: quitarla de `SHADOW_TIERS` tras validar ROI.

## Comandos

### Backend (local)
```bash
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```
Python 3.12. Deps: `pip install -r backend/requirements.txt`.

### Frontend
```bash
cd frontend-react && npm install && npm run build   # dist/
npm run dev    # http://localhost:5175 (proxy a backend:8002)
```

### Deploy a la VPS
```bash
bash scripts/deploy.sh backend|frontend|all
```
SCP + `systemctl restart smartodds-basketball-backend`. Sin git en la VPS.

## Producción (VPS2)

- **VPS2 `212.227.50.152`** (IONOS), la MISMA máquina que fútbol (8000/8001) y
  table tennis (8003). NO confundir con VPS1 `212.227.104.241` (tenis 8002 / TT 8003).
- Básquet en **puerto 8002** (libre en VPS2). App en `/opt/SmartOddsBasketball`,
  venv en `backend/venv`, SQLite, SSH con `~/.ssh/id_ed25519`.
- systemd `smartodds-basketball-backend` (enabled). nginx reverse-proxy a :8002 +
  Let's Encrypt (`certbot --nginx`, auto-renew). HTTP→HTTPS 301.
- Cron semanal (lunes 09:00 UTC): `scripts/cron_backtest.sh` → informe de backtest
  a Telegram SOLO si hay picks resueltos.

## Claves / APIs (compartidas)

- **The Odds API** — odds + scores (`/scores`). Misma `ODDS_API_KEY` que fútbol/tenis
  (plan 1M créditos/mes; básquet usa ~9-35k/mes). La clave real (32 chars) está en
  `/opt/SmartOdds/backend/.env` (fútbol). OJO: el `.env` de TT tiene un placeholder.
- **BetsAPI** — `BETSAPI_TOKEN` compartido. Cubre tenis/TT pero **NO básquet**
  (sport_id 18 → 403). `betsapi_odds_fetcher` está listo pero `BETSAPI_ODDS_ENABLED=false`.
  Para ACB/LNB hay que ampliar la cobertura de BetsAPI (de pago).
- **Telegram** — bot PROPIO de básquet (no reusar el de los otros, para no mezclar
  canales). Envía al chat personal. `.env` vive en la raíz de la app, no en `backend/`.

## Pendiente / futuro

- Salir de shadow tras calibrar (edge→ROI con datos acumulados).
- BetsAPI básquet (ACB) si se amplía el plan.
- Por portar de tenis (no urgente): BetBurger, auth/usuarios, PayPal/email,
  `calibrator` (Platt), `simulated_annealing` (re-optimización de pesos).
