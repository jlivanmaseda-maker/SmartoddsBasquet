/** Active picks page: card grid with league + shadow/active filters. */
import { useMemo, useState } from "react";
import { useQuery } from "../hooks/useQuery";
import { ACTIVE_PICKS_QUERY } from "../config/queries";
import {
  leagueLabel,
  normalizeLeague,
  type PickData,
} from "../config/constants";
import PickCard from "../components/PickCard";
import CalibrationBanner from "../components/CalibrationBanner";
import LoadingSpinner from "../components/LoadingSpinner";

type ShadowFilter = "all" | "active" | "shadow";

export default function PicksPage() {
  const { data, loading, error, refetch } = useQuery<{ activePicks: PickData[] }>(
    ACTIVE_PICKS_QUERY,
    {
      variables: { includeShadow: true, limit: 500 },
      pollInterval: 60000,
    },
  );

  const [leagueFilter, setLeagueFilter] = useState<string>("");
  const [shadowFilter, setShadowFilter] = useState<ShadowFilter>("all");

  const rawPicks = useMemo(() => data?.activePicks || [], [data]);

  const leagues = useMemo(() => {
    const set = new Set<string>();
    rawPicks.forEach((p) => {
      if (p.match.league) set.add(normalizeLeague(p.match.league));
    });
    return Array.from(set).sort();
  }, [rawPicks]);

  const picks = useMemo(() => {
    return rawPicks.filter((p) => {
      if (leagueFilter && normalizeLeague(p.match.league) !== leagueFilter) return false;
      if (shadowFilter === "active" && p.isShadow) return false;
      if (shadowFilter === "shadow" && !p.isShadow) return false;
      return true;
    });
  }, [rawPicks, leagueFilter, shadowFilter]);

  // Group by date (YYYY-MM-DD)
  const groups = useMemo(() => {
    const sorted = [...picks].sort(
      (a, b) =>
        new Date(a.match.commenceTime || 0).getTime() -
        new Date(b.match.commenceTime || 0).getTime(),
    );
    const map = new Map<string, PickData[]>();
    for (const p of sorted) {
      const d = p.match.commenceTime ? new Date(p.match.commenceTime) : null;
      const key = d
        ? d.toLocaleDateString("es-ES", { weekday: "long", day: "2-digit", month: "2-digit" })
        : "Sin fecha";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(p);
    }
    return Array.from(map.entries());
  }, [picks]);

  const avgEdge = picks.length
    ? picks.reduce((s, p) => s + p.edge, 0) / picks.length
    : 0;

  const SHADOW_TABS: { key: ShadowFilter; label: string }[] = [
    { key: "all", label: "Todos" },
    { key: "active", label: "Active" },
    { key: "shadow", label: "Shadow" },
  ];

  return (
    <div className="space-y-6">
      {/* Title + pills */}
      <div className="flex items-center gap-4 flex-wrap">
        <span className="font-mono font-bold text-[18px] md:text-[22px] text-[var(--v2-text-hero)] tracking-tight mr-2">
          Picks Activos
        </span>
        {picks.length > 0 && (
          <>
            <div className="flex items-center gap-1.5 bg-[var(--v2-bg-surface)] border border-[var(--v2-border-medium)] rounded-full px-3.5 py-1.5 text-[12.5px] font-medium text-[var(--v2-text-secondary)]">
              <span className="font-mono font-bold text-[13px] text-[var(--v2-gold)]">{picks.length}</span> picks
            </div>
            <div className="flex items-center gap-1.5 bg-[var(--v2-bg-surface)] border border-[var(--v2-border-medium)] rounded-full px-3.5 py-1.5 text-[12.5px] font-medium text-[var(--v2-text-secondary)]">
              Avg Edge{" "}
              <span className="font-mono font-bold text-[13px] text-[var(--v2-green)]">
                {avgEdge >= 0 ? "+" : ""}
                {avgEdge.toFixed(1)}%
              </span>
            </div>
          </>
        )}
      </div>

      <CalibrationBanner />

      {/* Filters */}
      <div className="flex flex-col gap-2 bg-[var(--v2-bg-card)] rounded-xl px-3 md:px-4 py-3 border border-[var(--v2-border-subtle)]">
        <div className="flex flex-wrap items-center gap-3">
          {/* Shadow tabs */}
          <div className="flex items-center gap-1.5">
            {SHADOW_TABS.map((t) => {
              const isActive = shadowFilter === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setShadowFilter(t.key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all border ${
                    isActive
                      ? "bg-[var(--v2-gold-dim)] border-[rgba(251,191,36,0.4)] text-[var(--v2-gold)]"
                      : "border-[var(--v2-border-medium)] text-[var(--v2-text-secondary)] hover:border-[var(--v2-border-accent)] hover:text-[var(--v2-text-primary)]"
                  }`}
                >
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* League select */}
          {leagues.length > 0 && (
            <div className="flex items-center gap-1.5 md:ml-auto">
              <span className="text-[10px] text-[var(--v2-text-muted)] uppercase tracking-wider">Liga</span>
              <select
                value={leagueFilter}
                onChange={(e) => setLeagueFilter(e.target.value)}
                className="bg-[var(--v2-bg-elevated)] border border-[var(--v2-border-medium)] rounded-md px-2 py-1 text-[11px] text-[var(--v2-text-primary)] outline-none focus:border-[var(--v2-border-accent)] transition-colors"
              >
                <option value="">Todas</option>
                {leagues.map((l) => (
                  <option key={l} value={l}>
                    {leagueLabel(l)}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between text-xs text-[var(--v2-text-muted)]">
        <span>{picks.length} picks encontrados</span>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1 hover:text-[var(--v2-text-secondary)] transition-colors"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refrescar
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-[rgba(239,68,68,0.3)] bg-[var(--v2-red-dim)] p-4 text-sm text-[var(--v2-red)]">
          Error al cargar picks: {error}
        </div>
      )}

      {loading && !data && <LoadingSpinner />}

      {/* Grouped card grid */}
      {groups.map(([label, groupPicks], gi) => (
        <div key={label} className={gi > 0 ? "mt-8" : ""}>
          <div className="flex items-center gap-2 mb-5 pb-2 border-b border-[var(--v2-border-subtle)]">
            <div className="w-1.5 h-1.5 rounded-full bg-[#f59e0b] shadow-[0_0_6px_#f59e0b]" />
            <span className="font-mono text-xs font-semibold uppercase tracking-widest text-[var(--v2-text-muted)]">
              {label}
            </span>
            <span className="font-mono text-xs text-[var(--v2-text-muted)]">({groupPicks.length})</span>
          </div>
          <div className="grid grid-cols-1 min-[900px]:grid-cols-2 min-[1400px]:grid-cols-3 gap-4">
            {groupPicks.map((p) => (
              <PickCard key={p.id} pick={p} />
            ))}
          </div>
        </div>
      ))}

      {!loading && picks.length === 0 && (
        <div className="text-center py-12">
          <p className="text-lg text-[var(--v2-text-secondary)]">No hay picks que coincidan</p>
          <p className="text-sm text-[var(--v2-text-muted)] mt-1">
            En fase de calibración la mayoría de picks están en SHADOW.
          </p>
        </div>
      )}
    </div>
  );
}
