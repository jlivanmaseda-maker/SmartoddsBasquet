/** Standings: ELO table per league with a league selector. */
import { useMemo, useState } from "react";
import { useQuery } from "../hooks/useQuery";
import { STANDINGS_QUERY } from "../config/queries";
import { leagueLabel, leagueColor, type StandingRow } from "../config/constants";
import LoadingSpinner from "../components/LoadingSpinner";

const LEAGUES = [
  { key: "wnba", label: "WNBA" },
  { key: "nba", label: "NBA" },
  { key: "euroleague", label: "EuroLeague" },
  { key: "ncaab", label: "NCAAB" },
];

export default function StandingsPage() {
  const [league, setLeague] = useState("wnba");

  const { data, loading, error } = useQuery<{ standings: StandingRow[] }>(
    STANDINGS_QUERY,
    { variables: { league, limit: 40 } },
  );

  const rows = useMemo(() => {
    const list = [...(data?.standings || [])];
    return list.sort((a, b) => (b.eloOverall || 0) - (a.eloOverall || 0));
  }, [data]);

  const accent = leagueColor(league);

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
          Clasificación ELO
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--v2-text-secondary)" }}>
          Ranking de equipos por rating ELO global
        </p>
      </div>

      {/* League selector */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {LEAGUES.map((l) => {
          const isActive = league === l.key;
          const c = leagueColor(l.key);
          return (
            <button
              key={l.key}
              onClick={() => setLeague(l.key)}
              className="px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all border"
              style={{
                color: isActive ? c : "var(--v2-text-secondary)",
                background: isActive ? `${c}1f` : "var(--v2-bg-card)",
                borderColor: isActive ? `${c}55` : "var(--v2-border-subtle)",
              }}
            >
              {l.label}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="rounded-lg border border-[rgba(239,68,68,0.3)] bg-[var(--v2-red-dim)] p-4 text-sm text-[var(--v2-red)]">
          Error al cargar clasificación: {error}
        </div>
      )}

      {loading && !data ? (
        <LoadingSpinner />
      ) : rows.length === 0 ? (
        <div
          className="rounded-xl p-6 border text-center"
          style={{ background: "var(--v2-bg-card)", borderColor: "var(--v2-border-subtle)" }}
        >
          <p className="text-sm" style={{ color: "var(--v2-text-muted)" }}>
            Sin datos de clasificación para {leagueLabel(league)}.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border" style={{ borderColor: "var(--v2-border-subtle)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "var(--v2-bg-elevated)" }}>
                <th className="px-3 py-3 text-left text-xs font-medium" style={{ color: "var(--v2-text-muted)" }}>#</th>
                <th className="px-3 py-3 text-left text-xs font-medium" style={{ color: "var(--v2-text-muted)" }}>Equipo</th>
                <th className="px-3 py-3 text-center text-xs font-medium" style={{ color: "var(--v2-text-muted)" }}>V</th>
                <th className="px-3 py-3 text-center text-xs font-medium" style={{ color: "var(--v2-text-muted)" }}>D</th>
                <th className="px-3 py-3 text-right text-xs font-medium" style={{ color: "var(--v2-text-muted)" }}>ELO</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t, i) => (
                <tr
                  key={t.id ?? t.name}
                  className="border-t hover:bg-[var(--v2-bg-elevated)] transition-colors"
                  style={{ borderColor: "var(--v2-border-subtle)" }}
                >
                  <td className="px-3 py-2.5 text-xs font-mono" style={{ color: "var(--v2-text-muted)" }}>
                    {i + 1}
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="inline-block w-1.5 h-4 rounded-sm" style={{ background: accent }} />
                      <span className="text-xs font-medium" style={{ color: "var(--v2-text-primary)" }}>
                        {t.name}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-center font-mono" style={{ color: "var(--v2-green)" }}>
                    {t.wins ?? 0}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-center font-mono" style={{ color: "var(--v2-red)" }}>
                    {t.losses ?? 0}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-right font-mono font-bold" style={{ color: "var(--v2-gold)" }}>
                    {t.eloOverall != null ? t.eloOverall.toFixed(0) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
