/** GraphQL query strings for the SmartOdds Basket backend (camelCase fields). */

const PICK_FIELDS = `
  id
  betType
  bestOdds
  bestBookmaker
  edge
  estimatedProbability
  isActive
  isShadow
  shadowReasons
  result
  profitUnits
  clvPct
  createdAt
  match {
    id
    league
    leagueTier
    homeTeam
    awayTeam
    commenceTime
    isCompleted
    score
    probHome
    probAway
  }
`;

export const STATS_QUERY = `
  query Stats($includeShadow: Boolean) {
    stats(includeShadow: $includeShadow) {
      totalPicks
      resolved
      won
      lost
      void
      profitUnits
      roiPct
      winratePct
      activePicks
      shadowPicks
      clvN
      avgClvPct
      clvPositivePct
    }
  }
`;

export const ACTIVE_PICKS_QUERY = `
  query ActivePicks($includeShadow: Boolean, $limit: Int) {
    activePicks(includeShadow: $includeShadow, limit: $limit) {
      ${PICK_FIELDS}
    }
  }
`;

export const RESOLVED_PICKS_QUERY = `
  query ResolvedPicks($includeShadow: Boolean, $limit: Int) {
    resolvedPicks(includeShadow: $includeShadow, limit: $limit) {
      ${PICK_FIELDS}
    }
  }
`;

export const STANDINGS_QUERY = `
  query Standings($league: String, $limit: Int) {
    standings(league: $league, limit: $limit) {
      id
      name
      league
      eloOverall
      wins
      losses
    }
  }
`;

export const SYSTEM_CONFIG_QUERY = `
  query SystemConfig {
    systemConfig
  }
`;

/** Dashboard bundle: stats + active + resolved in one round trip. */
export const DASHBOARD_QUERY = `
  query Dashboard($includeShadow: Boolean, $activeLimit: Int, $resolvedLimit: Int) {
    stats(includeShadow: $includeShadow) {
      totalPicks
      resolved
      won
      lost
      void
      profitUnits
      roiPct
      winratePct
      activePicks
      shadowPicks
      clvN
      avgClvPct
      clvPositivePct
    }
    activePicks(includeShadow: $includeShadow, limit: $activeLimit) {
      ${PICK_FIELDS}
    }
    resolvedPicks(includeShadow: $includeShadow, limit: $resolvedLimit) {
      ${PICK_FIELDS}
    }
    systemConfig
  }
`;

/** Pagina /picks (25-oct-2026): la sombra por regla y mercado + estado del sistema (ver backend schemas/sombra.py). */
export const SHADOW_RULES_QUERY = `
  query ShadowRules($dias: Int) {
    systemStatus {
      version
      reglaGanador
      reglaLineas
      lineasActivas
      vigilanteOk
      vigilanteFallos
      vigilanteActualizado
      creditosRestantes
    }
    shadowRules(dias: $dias) {
      clave
      regla
      mercado
      nombre
      descripcion
      desde
      picks
      abiertos
      liquidados
      ganados
      nulos
      unidades
      roi
      roiError
      roiMediana
      roiMedianaError
      nMediana
      clv
      clvPositivos
      nClv
      lineaVsCierre
      nLinea
      cuotaMedia
      objetivo
      cumpleUmbral
    }
  }
`;

export const SHADOW_PICKS_QUERY = `
  query ShadowPicks($dias: Int, $clave: String, $estado: String, $liga: String, $limit: Int) {
    shadowPicks(dias: $dias, clave: $clave, estado: $estado, liga: $liga, limit: $limit) {
      id
      clave
      reglaNombre
      mercado
      liga
      inicio
      creado
      horasAntes
      local
      visitante
      seleccion
      cuota
      casa
      cuotaMediana
      nCasas
      cuotaMinima
      pinnacleJusta
      edge
      estado
      beneficio
      clv
      cuotaCierreJusta
      lineaVsCierre
      marcador
      casas {
        casa
        cuota
      }
    }
  }
`;
