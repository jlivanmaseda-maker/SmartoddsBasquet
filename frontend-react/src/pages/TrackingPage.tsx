/** Tracking: resolved picks, aggregate stats, ROI-by-league + cumulative charts. */
import { useMemo, useState, lazy, Suspense } from "react";
import { useQuery } from "../hooks/useQuery";
import { STATS_QUERY, RESOLVED_PICKS_QUERY } from "../config/queries";
import {
  formatBetType,
  formatBookmaker,
  formatDate,
  formatProfit,
  leagueLabel,
  normalizeLeague,
  type PickData,
  type StatsData,
} from "../config/constants";
import StatCard from "../components/StatCard";
import StatsGrid from "../components/StatsGrid";
import ProfitBanner from "../components/tracking/ProfitBanner";
import LeagueBadge from "../components/LeagueBadge";
import LoadingSpinner from "../components/LoadingSpinner";

const EvolutionChart = lazy(() => import("../components/tracking/EvolutionChart"));
const RoiByLeagueChart = lazy(() => import("../components/tracking/RoiByLeagueChart"));

export default function TrackingPage() {
  const { data: statsData } = useQuery<{ stats: StatsData }>(STATS_QUERY, {
    variables: { includeShadow: true },
    pollInterval: 60000,
  });
  const { data, loading } = useQuery<{ resolvedPicks: PickData[] }>(
    RESOLVED_PICKS_QUERY,
    { variables: { includeShadow: true, limit: 5000 }, pollInterval: 60000 },
  );

  const stats = statsData?.stats;
  const resolvedPicks = useMemo(() => data?.resolvedPicks || [], [data]);

  const [leagueFilter, setLeagueFilter] = useState("");

  const leagues = useMemo(() => {
    const set = new Set<string>();
    resolvedPicks.forEach((p) => p.match.league && set.add(normalizeLeague(p.match.league)));
    return Array.from(set).sort();
  }, [resolvedPicks]);

  const filtered = useMemo(
    () =>
      leagueFilter
        ? resolvedPicks.filter((p) => normalizeLeague(p.match.league) === leagueFilter)
        : resolvedPicks,
    [resolvedPicks, leagueFilter],
  );

  if (loading && !data) return <LoadingSpinner />;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div
        className="rounded-xl p-4 md:p-5 border"
        style={{
          background: "linear-gradient(to right, var(--v2-bg-card), var(--v2-bg-elevated))",
          borderColor: "var(--v2-border-subtle)",
        }}
      >
        <h1 className="text-xl md:text-2xl font-bold" style={{ color: "var(--v2-text-hero)" }}>
          Tracking
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--v2-text-secondary)" }}>
          Análisis de rendimiento del sistema (paper trading · 1u flat)
        </p>
      </div>

      {/* Profit banner */}
      <ProfitBanner
        title="Profit Total"
        value={stats?.profitUnits || 0}
        suffix="u"
        accentColor="auto"
        secondaryText={`ROI: ${(stats?.roiPct || 0).toFixed(1)}% · ${stats?.resolved || 0} picks resueltos`}
      />

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Win Rate" value={`${(stats?.winratePct || 0).toFixed(1)}%`} color={(stats?.winratePct || 0) >= 50 ? "green" : "red"} />
        <StatCard label="Ganados" value={stats?.won || 0} color="green" />
        <StatCard label="Perdidos" value={stats?.lost || 0} color="red" />
        <StatCard label="En Shadow" value={stats?.shadowPicks || 0} color="gold" />
      </div>

      <StatsGrid
        title="Estadísticas del Sistema"
        columns={3}
        items={[
          { label: "Picks Totales", value: stats?.totalPicks || 0 },
          { label: "Resueltos", value: stats?.resolved || 0 },
          { label: "Activos", value: stats?.activePicks || 0, color: "gold" },
          { label: "Ganados", value: stats?.won || 0, color: "green" },
          { label: "Perdidos", value: stats?.lost || 0, color: "red" },
          { label: "Nulos", value: stats?.void || 0 },
          { label: "Win Rate", value: `${(stats?.winratePct || 0).toFixed(1)}%`, color: (stats?.winratePct || 0) >= 50 ? "green" : "red" },
          { label: "ROI", value: `${(stats?.roiPct || 0).toFixed(1)}%`, color: (stats?.roiPct || 0) >= 0 ? "green" : "red" },
          { label: "Profit", value: `${(stats?.profitUnits || 0).toFixed(2)}u`, color: (stats?.profitUnits || 0) >= 0 ? "green" : "red" },
        ]}
      />

      {/* Cumulative profit chart */}
      <div
        className="rounded-xl p-5 border"
        style={{ background: "var(--v2-bg-card)", borderColor: "var(--v2-border-subtle)" }}
      >
        <h3 className="text-[11px] uppercase tracking-wider font-semibold mb-3.5" style={{ color: "var(--v2-text-muted)" }}>
          Evolución del Profit
        </h3>
        <Suspense fallback={<div style={{ height: 320 }} />}>
          <EvolutionChart picks={resolvedPicks} height={320} />
        </Suspense>
      </div>

      {/* ROI by league chart */}
      <div
        className="rounded-xl p-5 border"
        style={{ background: "var(--v2-bg-card)", borderColor: "var(--v2-border-subtle)" }}
      >
        <h3 className="text-[11px] uppercase tracking-wider font-semibold mb-3.5" style={{ color: "var(--v2-text-muted)" }}>
          Profit por Liga
        </h3>
        <Suspense fallback={<div style={{ height: 280 }} />}>
          <RoiByLeagueChart picks={resolvedPicks} height={280} />
        </Suspense>
      </div>

      {/* Resolved picks table */}
      <div
        className="rounded-xl p-5 border"
        style={{ background: "var(--v2-bg-card)", borderColor: "var(--v2-border-subtle)" }}
      >
        <div className="flex items-center justify-between mb-3.5 gap-3 flex-wrap">
          <h3 className="text-[11px] uppercase tracking-wider font-semibold" style={{ color: "var(--v2-text-muted)" }}>
            Picks Resueltos
            <span className="text-xs font-normal ml-2" style={{ color: "var(--v2-text-secondary)" }}>
              ({filtered.length})
            </span>
          </h3>
          {leagues.length > 0 && (
            <select
              value={leagueFilter}
              onChange={(e) => setLeagueFilter(e.target.value)}
              className="bg-[var(--v2-bg-elevated)] border border-[var(--v2-border-medium)] rounded-md px-2 py-1 text-[11px] text-[var(--v2-text-primary)] outline-none"
            >
              <option value="">Todas las ligas</option>
              {leagues.map((l) => (
                <option key={l} value={l}>
                  {leagueLabel(l)}
                </option>
              ))}
            </select>
          )}
        </div>

        {filtered.length === 0 ? (
          <div className="text-center py-12" style={{ color: "var(--v2-text-muted)" }}>
            Aún no hay picks resueltos.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "var(--v2-border-subtle)" }}>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "var(--v2-bg-elevated)" }}>
                  {["Fecha", "Partido", "Liga", "Marcador", "Apuesta", "Cuota", "Casa", "Resultado", "Profit"].map((h) => (
                    <th key={h} className="px-3 py-3 text-left text-xs font-medium" style={{ color: "var(--v2-text-muted)" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => {
                  const isWon = p.result === "won";
                  const isVoid = p.result === "void";
                  const rowBg = isWon
                    ? "rgba(34, 197, 94, 0.05)"
                    : isVoid
                      ? "transparent"
                      : "rgba(239, 68, 68, 0.05)";
                  return (
                    <tr
                      key={p.id}
                      className="border-t hover:bg-[var(--v2-bg-elevated)] transition-colors"
                      style={{ borderColor: "var(--v2-border-subtle)", background: rowBg }}
                    >
                      <td className="px-3 py-2.5 whitespace-nowrap text-xs" style={{ color: "var(--v2-text-secondary)" }}>
                        {formatDate(p.createdAt)}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="text-xs font-medium" style={{ color: "var(--v2-text-primary)" }}>
                          {p.match.homeTeam} vs {p.match.awayTeam}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <LeagueBadge league={p.match.league} />
                      </td>
                      <td className="px-3 py-2.5 text-xs" style={{ color: "var(--v2-text-muted)" }}>
                        {p.match.score || "—"}
                      </td>
                      <td className="px-3 py-2.5 text-xs font-medium" style={{ color: "var(--v2-gold)" }}>
                        {formatBetType(p.betType, p.match)}
                      </td>
                      <td className="px-3 py-2.5 text-xs font-mono" style={{ color: "var(--v2-text-primary)" }}>
                        {p.bestOdds.toFixed(2)}
                      </td>
                      <td className="px-3 py-2.5 text-xs" style={{ color: "var(--v2-text-secondary)" }}>
                        {formatBookmaker(p.bestBookmaker)}
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-md text-[10px] font-bold uppercase ${
                            isWon
                              ? "bg-green-500/20 text-green-400"
                              : isVoid
                                ? "bg-gray-500/20 text-gray-400"
                                : "bg-red-500/20 text-red-400"
                          }`}
                        >
                          {(p.result || "").toUpperCase()}
                        </span>
                      </td>
                      <td
                        className="px-3 py-2.5 text-xs font-bold font-mono"
                        style={{ color: (p.profitUnits || 0) >= 0 ? "var(--v2-green)" : "var(--v2-red)" }}
                      >
                        {formatProfit(p.profitUnits)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
