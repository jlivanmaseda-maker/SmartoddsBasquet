// Constantes y helpers de UI para SmartOdds Basketball.
// Adaptado de tenis: en vez de colores por superficie, badges por liga.

/* ============================================================
   TYPES (match the basketball GraphQL schema)
   ============================================================ */

export interface MatchData {
  id?: number | string;
  league: string;
  leagueTier?: string | null;
  homeTeam: string;
  awayTeam: string;
  commenceTime?: string | null;
  isCompleted?: boolean;
  score?: string | null;
  probHome?: number | null;
  probAway?: number | null;
}

export interface PickData {
  id: number | string;
  betType: string;
  bestOdds: number;
  bestBookmaker: string;
  edge: number;
  estimatedProbability: number;
  isActive?: boolean;
  isShadow?: boolean;
  shadowReasons?: string[] | string | null;
  result?: string | null;
  profitUnits?: number | null;
  clvPct?: number | null;
  createdAt?: string | null;
  match: MatchData;
}

export interface StatsData {
  totalPicks: number;
  resolved: number;
  won: number;
  lost: number;
  void: number;
  profitUnits: number;
  roiPct: number;
  winratePct: number;
  activePicks: number;
  shadowPicks: number;
  clvN?: number;
  avgClvPct?: number | null;
  clvPositivePct?: number | null;
}

export interface StandingRow {
  id: number | string;
  name: string;
  league: string;
  eloOverall: number;
  wins: number;
  losses: number;
}

/* ============================================================
   LEAGUE METADATA
   ============================================================ */

// Both bare keys (nba) and prefixed keys (basketball_nba) supported.
export const LEAGUE_LABELS: Record<string, string> = {
  nba: "NBA",
  "nba summer league": "Summer League",
  wnba: "WNBA",
  ncaab: "NCAAB",
  euroleague: "EuroLeague",
  nbl: "NBL",
  basketball_nba: "NBA",
  basketball_wnba: "WNBA",
  basketball_ncaab: "NCAAB",
  basketball_euroleague: "EuroLeague",
  basketball_nbl: "NBL",
};

export const LEAGUE_COLORS: Record<string, string> = {
  nba: "#C8102E", // rojo NBA
  "nba summer league": "#F58426", // naranja verano
  wnba: "#FF6900",
  ncaab: "#0067B1",
  euroleague: "#EF7F1A",
  nbl: "#00843D",
  basketball_nba: "#C8102E",
  basketball_wnba: "#FF6900",
  basketball_ncaab: "#0067B1",
  basketball_euroleague: "#EF7F1A",
  basketball_nbl: "#00843D",
};

export function normalizeLeague(league?: string | null): string {
  if (!league) return "";
  return league.replace(/^basketball_/, "").toLowerCase();
}

export function leagueLabel(league?: string | null): string {
  if (!league) return "—";
  const key = normalizeLeague(league);
  return LEAGUE_LABELS[key] || LEAGUE_LABELS[league] || key.toUpperCase();
}

export function leagueColor(league?: string | null): string {
  const key = normalizeLeague(league);
  return LEAGUE_COLORS[key] || LEAGUE_COLORS[league || ""] || "#94a3b8";
}

/* ============================================================
   MARKET / BET TYPE LABELS
   ============================================================ */

export const MARKET_LABELS: Record<string, string> = {
  match_winner_home: "Ganador (Local)",
  match_winner_away: "Ganador (Visitante)",
  spread_home: "Hándicap (Local)",
  spread_away: "Hándicap (Visitante)",
  total_points_over: "Más de puntos",
  total_points_under: "Menos de puntos",
};

/** Human-friendly bet label; falls back to a prettified betType. */
export function formatBetType(betType: string, match?: MatchData): string {
  if (betType === "match_winner_home" && match) return `Ganador: ${match.homeTeam}`;
  if (betType === "match_winner_away" && match) return `Ganador: ${match.awayTeam}`;
  if (MARKET_LABELS[betType]) return MARKET_LABELS[betType];
  return betType
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Base market for grouping (strip _home/_away suffix). */
export function baseMarket(betType: string): string {
  return betType.replace(/_(home|away|over|under)$/, "");
}

const BOOKMAKER_LABELS: Record<string, string> = {
  pinnacle: "Pinnacle",
  bet365: "Bet365",
  williamhill: "William Hill",
  betfair: "Betfair",
  unibet: "Unibet",
  marathonbet: "Marathonbet",
  betano: "Betano",
};

export function formatBookmaker(bk?: string | null): string {
  if (!bk) return "—";
  return BOOKMAKER_LABELS[bk.toLowerCase()] || bk.replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ============================================================
   FORMATTERS
   ============================================================ */

export function formatDate(s?: string | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return s;
  }
}

export function formatDateShort(s?: string | null): string {
  if (!s) return "—";
  try {
    const d = new Date(s);
    const now = new Date();
    const isToday =
      d.getDate() === now.getDate() &&
      d.getMonth() === now.getMonth() &&
      d.getFullYear() === now.getFullYear();
    const time = d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });
    if (isToday) return `Hoy ${time}`;
    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    return `${dd}/${mm} ${time}`;
  } catch {
    return s;
  }
}

export function formatProfit(v?: number | null): string {
  const n = v || 0;
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}u`;
}

export function formatEdge(v?: number | null): string {
  const n = v || 0;
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}
