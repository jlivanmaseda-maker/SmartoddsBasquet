/** Dashboard: stats cards, recent picks, profit-evolution chart. */
import { useMemo, lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "../hooks/useQuery";
import { DASHBOARD_QUERY } from "../config/queries";
import {
  formatBetType,
  formatDate,
  type PickData,
  type StatsData,
} from "../config/constants";
import StatCard from "../components/StatCard";
import LeagueBadge from "../components/LeagueBadge";
import CalibrationBanner from "../components/CalibrationBanner";
import ProfitBanner from "../components/tracking/ProfitBanner";
import LoadingSpinner from "../components/LoadingSpinner";

const EvolutionChart = lazy(() => import("../components/tracking/EvolutionChart"));

interface DashboardData {
  stats: StatsData;
  activePicks: PickData[];
  resolvedPicks: PickData[];
  systemConfig: Record<string, unknown> | null;
}

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 pt-2">
      <h2
        className="text-[10px] font-bold uppercase tracking-widest"
        style={{ color: "var(--v2-text-muted)" }}
      >
        {label}
      </h2>
      <div className="flex-1 border-t" style={{ borderColor: "var(--v2-border-subtle)" }} />
    </div>
  );
}

export default function DashboardPage() {
  const { data, loading, error } = useQuery<DashboardData>(DASHBOARD_QUERY, {
    variables: { includeShadow: true, activeLimit: 200, resolvedLimit: 1000 },
    pollInterval: 60000,
  });

  const stats = data?.stats;
  const activePicks = useMemo(() => data?.activePicks || [], [data]);
  const resolvedPicks = useMemo(() => data?.resolvedPicks || [], [data]);
  const recentPicks = activePicks.slice(0, 8);

  if (loading && !data) return <LoadingSpinner />;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div
        className="rounded-xl p-4 md:p-6 border"
        style={{
          background: "linear-gradient(to right, var(--v2-bg-card), var(--v2-bg-elevated))",
          borderColor: "var(--v2-border-subtle)",
        }}
      >
        <h1 className="text-2xl font-bold" style={{ color: "var(--v2-text-hero)" }}>
          Dashboard
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--v2-text-secondary)" }}>
          Value betting de baloncesto · modelo ELO + ensemble
        </p>
      </div>

      <CalibrationBanner />

      {error && (
        <div className="rounded-lg border border-[rgba(239,68,68,0.3)] bg-[var(--v2-red-dim)] p-4 text-sm text-[var(--v2-red)]">
          Error al cargar datos: {error}
        </div>
      )}

      {/* Quick metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
        <StatCard
          label="Profit"
          value={`${(stats?.profitUnits || 0) >= 0 ? "+" : ""}${(stats?.profitUnits || 0).toFixed(2)}`}
          suffix="u"
          color={(stats?.profitUnits || 0) >= 0 ? "green" : "red"}
        />
        <StatCard
          label="ROI"
          value={`${(stats?.roiPct || 0).toFixed(1)}%`}
          color={(stats?.roiPct || 0) >= 0 ? "green" : "red"}
          subtitle={
            stats?.avgClvPct == null
              ? undefined
              : `CLV ${stats.avgClvPct > 0 ? "+" : ""}${stats.avgClvPct.toFixed(1)}% · ${(stats.clvPositivePct ?? 0).toFixed(0)}% >0`
          }
        />
        <StatCard
          label="Winrate"
          value={`${(stats?.winratePct || 0).toFixed(1)}%`}
          color="gold"
        />
        <Link to="/picks">
          <StatCard label="Picks Activos" value={stats?.activePicks || 0} color="gold" />
        </Link>
      </div>

      {/* Resumen */}
      <SectionHeader label="Resumen" />
      <ProfitBanner
        title="Profit Total (Paper Trading · 1u flat)"
        value={stats?.profitUnits || 0}
        suffix="u"
        accentColor="auto"
        secondaryText={`ROI: ${(stats?.roiPct || 0).toFixed(1)}% · ${stats?.resolved || 0} resueltos · ${stats?.shadowPicks || 0} en shadow`}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Picks Totales" value={stats?.totalPicks || 0} />
        <StatCard label="Ganados" value={stats?.won || 0} color="green" />
        <StatCard label="Perdidos" value={stats?.lost || 0} color="red" />
        <StatCard label="Nulos" value={stats?.void || 0} color="gold" />
      </div>

      {/* Evolution chart */}
      <SectionHeader label="Evolución del Profit" />
      <div
        className="rounded-xl p-5 border"
        style={{ background: "var(--v2-bg-card)", borderColor: "var(--v2-border-subtle)" }}
      >
        <h3
          className="text-xs font-semibold uppercase tracking-wider mb-4"
          style={{ color: "var(--v2-text-secondary)" }}
        >
          Profit acumulado (picks resueltos)
        </h3>
        <Suspense
          fallback={
            <div
              className="flex items-center justify-center text-sm"
              style={{ height: 300, color: "var(--v2-text-secondary)" }}
            >
              Cargando gráfico…
            </div>
          }
        >
          <EvolutionChart picks={resolvedPicks} height={300} />
        </Suspense>
      </div>

      {/* Recent picks */}
      <SectionHeader label="Picks Recientes" />
      {recentPicks.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "var(--v2-border-subtle)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "var(--v2-bg-elevated)" }}>
                {["Partido", "Liga", "Apuesta", "Cuota", "Edge", "Estado", "Fecha"].map((h, i) => (
                  <th
                    key={h}
                    className={`px-3 py-3 text-xs font-medium ${i >= 3 && i <= 4 ? "text-center" : "text-left"}`}
                    style={{ color: "var(--v2-text-muted)" }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recentPicks.map((p) => (
                <tr
                  key={p.id}
                  className="border-t hover:bg-[var(--v2-bg-elevated)] transition-colors"
                  style={{ borderColor: "var(--v2-border-subtle)" }}
                >
                  <td className="px-3 py-2.5">
                    <span className="text-xs font-medium" style={{ color: "var(--v2-text-primary)" }}>
                      {p.match.homeTeam} vs {p.match.awayTeam}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <LeagueBadge league={p.match.league} />
                  </td>
                  <td className="px-3 py-2.5 text-xs font-medium" style={{ color: "var(--v2-gold)" }}>
                    {formatBetType(p.betType, p.match)}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-center font-mono" style={{ color: "var(--v2-text-primary)" }}>
                    {(p.bestOdds ?? 0).toFixed(2)}
                  </td>
                  <td
                    className="px-3 py-2.5 text-xs text-center font-mono font-semibold"
                    style={{ color: (p.edge ?? 0) >= 0 ? "var(--v2-green)" : "var(--v2-red)" }}
                  >
                    {(p.edge ?? 0) >= 0 ? "+" : ""}
                    {(p.edge ?? 0).toFixed(1)}%
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                        p.isShadow
                          ? "bg-[var(--v2-gold-dim)] text-[var(--v2-gold)]"
                          : "bg-green-500/20 text-green-400"
                      }`}
                    >
                      {p.isShadow ? "SHADOW" : "ACTIVE"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap text-xs" style={{ color: "var(--v2-text-secondary)" }}>
                    {formatDate(p.match.commenceTime)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div
          className="rounded-xl p-6 border text-center"
          style={{ background: "var(--v2-bg-card)", borderColor: "var(--v2-border-subtle)" }}
        >
          <p className="text-sm" style={{ color: "var(--v2-text-muted)" }}>
            Sin picks abiertos ahora mismo.
          </p>
        </div>
      )}
    </div>
  );
}
