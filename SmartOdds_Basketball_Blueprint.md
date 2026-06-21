# SmartOdds Basketball — Blueprint

Documento de arquitectura. Portado de **SmartOdds Tennis** (el proyecto que
mejor funciona) al baloncesto. El core es **agnostico al deporte**: fetch odds
→ modelo → edge/Kelly → resolucion → ELO. Cambian el modelo de datos (equipos)
y la logica especifica del deporte.

---

## 1. Vision

Detectar value bets en basket comparando la probabilidad estimada por un
ensemble ML contra las cuotas de mercado, usando las casas sharp (Pinnacle/
1xBet) como referencia principal (BookDif + CLV). Picks por Telegram + web.

## 2. Stack (identico a tenis)

- **Backend:** Python 3.12, FastAPI, Strawberry GraphQL, SQLAlchemy, APScheduler.
- **ML:** scikit-learn, LightGBM, numpy, pandas.
- **Frontend:** React 19, TypeScript, Vite, Apollo, TailwindCSS, Recharts.
- **DB:** SQLite (dev) / PostgreSQL (prod).
- **Infra:** VPS2 IONOS (212.227.50.152, junto a futbol), systemd, Nginx,
  deploy por SCP. Puerto backend **8002** (futbol usa 8000/8001).

## 3. Adaptaciones Tenis → Basket

| Concepto | Tenis | Basket |
|----------|-------|--------|
| Competidor | Jugador (Player) | Equipo (Team) |
| Contexto | Superficie | Liga + ventaja de cancha |
| Rating | ELO por superficie | ELO equipo + ELO local/visitante |
| Marcador | Sets / games | Puntos / cuartos / prorroga |
| Void | Retirada / walkover | Partido aplazado / cancelado |
| Empate | No (2 vias) | No (2 vias; desempate = prorroga) |
| Senales propias | Saque, fatiga de partidos | Net Rating (ORtg/DRtg), pace, back-to-back |
| H2H | Valor medio-alto | Valor bajo (rotacion de plantillas) |

## 4. Modelo de datos

- **Team** — ELO global/local/visitante, ORtg, DRtg, Net Rating, pace, forma,
  back-to-back, standings. (+ `TeamNameAlias` para casar fuentes).
- **Match** — local/visitante, liga, puntos, prorroga, lineas de spread/total,
  dias de descanso, probabilidades del modelo.
- **Odds / OddsHistory** — moneyline (2 vias), spread, totals por bookmaker.
- **Pick / UserBet / PickModelDetail** — edge, bookdif, CLV, resultado, desglose
  por componente del ensemble.
- **User** — auth JWT, bankroll, suscripcion PayPal, verificacion email.

## 5. Ensemble ML (componentes y pesos placeholder)

1. **ELO Team** (0.40) — ELO + ventaja de cancha (`ELO_HOME_ADVANTAGE`).
2. **Net Rating** (0.25) — ORtg − DRtg, ajustado por pace.
3. **Form** (0.15) — win rate ultimos 10 partidos.
4. **Rest/Fatiga** (0.10) — back-to-back y dias de descanso.
5. **Home Court** (0.05) — ventaja de local.
6. **H2H** (0.05) — enfrentamientos recientes.

Calibracion por liga (Platt). Pesos re-optimizados semanalmente (SA). Para
basket es muy recomendable el **margen de victoria (MOV)** en el update de ELO.

## 6. Mercados

- **Dia 1:** Match Winner (moneyline, 2 vias).
- **Shadow (trackear sin mostrar):** spread (hándicap de puntos), totals (O/U).
- Mas adelante: cuartos/mitades, player props.

## 7. Ciclo del scheduler (15 min)

```
T+0   odds_fetcher          The Odds API -> Match + Odds
T+5   betsapi (ligas menores)
T+12  value_calculator      edge >= MIN_EDGE -> Pick (shadow si no hay sharp)
T+15  score_resolver        points_home/away -> won/lost/void
T+20  elo_calculator        update ELO de equipo (K por liga, ventaja cancha)
Lunes simulated_annealing   re-optimiza pesos
```

## 8. Estrategia sharp

Identica a tenis: avg-line devigged de Pinnacle + 1xBet como senal primaria;
picks sin sharp → shadow automatico; filtro de lineas corruptas (sharp > 3x
mediana soft).

## 9. Ligas y fases (todas al principio)

Empezar amplio (NBA + EuroLeague + NCAA + WNBA), trackear NCAA en shadow por
alto ruido, y filtrar por rentabilidad con backtest — igual que ITF/Challenger
en tenis. Definir cuales pasan a ACTIVE segun ROI + CLV.

## 10. Errores a evitar (heredados de tenis/futbol)

- No activar una liga hasta validar rentabilidad en shadow (caso ITF).
- No cambiar pesos/filtros/ligas sin backtest que lo respalde.
- Mantener el aislamiento total respecto a los otros deportes.

## 11. Roadmap

1. Confirmar proveedor de scores + cobertura odds de The Odds API en basket.
2. Portar odds_fetcher → value_calculator → score_resolver → scheduler.
3. Completar ensemble + seed de ELO historico + backtest.
4. Calibrar edge minimo y pesos (SA).
5. GraphQL + frontend (PickCard con badge de liga).
6. Deploy en VPS2 212.227.50.152 (:8002) y fase shadow antes de publicar picks.
