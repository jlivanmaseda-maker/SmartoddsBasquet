/** Basketball pick card matching tennis/football design. */
import {
  formatBetType,
  formatBookmaker,
  formatDateShort,
  leagueColor,
  type PickData,
} from "../config/constants";
import LeagueBadge from "./LeagueBadge";

interface PickCardProps {
  pick: PickData;
}

export default function PickCard({ pick }: PickCardProps) {
  const { match, betType, edge, bestOdds, bestBookmaker, estimatedProbability } = pick;
  const isValue = edge > 0;
  const isHighEdge = edge >= 5;
  const isShadow = !!pick.isShadow;
  const accent = leagueColor(match.league);
  const betLabel = formatBetType(betType, match);

  return (
    <div
      className="relative bg-[var(--v2-bg-card)] rounded-2xl overflow-hidden border border-[var(--v2-border-subtle)] transition-all duration-300 hover:-translate-y-[3px] hover:border-[var(--v2-border-accent)]"
      style={{ boxShadow: "0 1px 3px rgba(0,0,0,0.4), 0 8px 24px rgba(0,0,0,0.25)" }}
    >
      {/* Left accent border (league colored) */}
      <div
        className="absolute top-0 left-0 w-[3px] h-full rounded-l-2xl z-[2]"
        style={{ background: isShadow ? "var(--v2-gold)" : accent }}
      />

      {isHighEdge && !isShadow && (
        <div className="absolute inset-0 rounded-2xl pointer-events-none z-0 bg-gradient-to-br from-[rgba(34,197,94,0.1)] via-[rgba(34,197,94,0.02)] to-transparent" />
      )}

      <div className="relative z-[1] flex flex-col pt-[12px] pr-[14px] pb-[12px] pl-[16px]">
        {/* Header: league + tier + time + shadow/active */}
        <div className="flex items-center justify-between mb-[6px] gap-2">
          <div className="flex items-center gap-[6px] min-w-0 flex-1">
            <LeagueBadge league={match.league} tier={match.leagueTier} />
            {isShadow ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-[var(--v2-gold-dim)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--v2-gold)] border border-[rgba(251,191,36,0.3)] flex-shrink-0">
                Shadow
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-[var(--v2-green-dim)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--v2-green)] border border-[rgba(34,197,94,0.3)] flex-shrink-0">
                Active
              </span>
            )}
          </div>
          <span className="text-[10px] font-mono font-medium text-[var(--v2-text-muted)] flex-shrink-0">
            {formatDateShort(match.commenceTime)}
          </span>
        </div>

        {/* Teams (hero) */}
        <div className="flex items-center gap-2 mb-[6px] flex-wrap">
          <span className="text-[14px] md:text-[16px] font-bold text-[var(--v2-text-hero)] tracking-tight">
            {match.homeTeam}
          </span>
          <span className="text-[11px] text-[var(--v2-text-muted)] font-medium">vs</span>
          <span className="text-[14px] md:text-[16px] font-bold text-[var(--v2-text-hero)] tracking-tight">
            {match.awayTeam}
          </span>
        </div>

        {/* Market + best bookmaker */}
        <div className="flex items-center gap-[5px] mb-[8px] flex-wrap">
          <span className="text-[11px] font-bold uppercase tracking-wide px-2 py-[2px] rounded-md bg-[var(--v2-border-medium)] text-[var(--v2-text-primary)] border border-[var(--v2-border-accent)]">
            {betLabel}
          </span>
          <span className="text-[10px] font-semibold uppercase tracking-wide px-2 py-[2px] rounded-md bg-gradient-to-r from-[rgba(34,197,94,0.15)] to-[rgba(34,197,94,0.08)] text-[var(--v2-green)] border border-[rgba(34,197,94,0.2)]">
            Best: {formatBookmaker(bestBookmaker)}
          </span>
        </div>

        {/* Odds + edge + prob */}
        <div className="flex items-end gap-x-2.5 gap-y-1 flex-wrap">
          <span
            className={`text-[28px] md:text-[36px] font-mono font-extrabold leading-none tracking-tighter ${
              isValue ? "text-[var(--v2-text-hero)]" : "text-[var(--v2-text-secondary)]"
            }`}
          >
            {bestOdds.toFixed(2)}
          </span>
          <span
            className={`inline-flex items-center gap-1 text-[11px] font-mono font-bold px-2 py-[2px] rounded-md w-fit mb-1 ${
              isValue
                ? "bg-gradient-to-r from-[rgba(34,197,94,0.2)] to-[rgba(34,197,94,0.1)] text-[var(--v2-green)] border border-[rgba(34,197,94,0.25)]"
                : "bg-[rgba(239,68,68,0.1)] text-[var(--v2-red)] border border-[rgba(239,68,68,0.2)]"
            }`}
          >
            {edge >= 0 ? "▲" : "▼"} {edge >= 0 ? "+" : ""}
            {edge.toFixed(1)}%
          </span>
          {estimatedProbability > 0 && (
            <span className="inline-flex items-center text-[10px] font-mono font-semibold px-1.5 py-[2px] rounded-md mb-1 bg-[rgba(59,130,246,0.1)] text-[var(--v2-blue)] border border-[rgba(59,130,246,0.2)]">
              Prob {(estimatedProbability * 100).toFixed(0)}%
            </span>
          )}
        </div>

        {/* Shadow reasons */}
        {isShadow && pick.shadowReasons && pick.shadowReasons.length > 0 && (
          <div className="mt-[8px] pt-[8px] border-t border-[var(--v2-border-subtle)] flex flex-wrap gap-1">
            {pick.shadowReasons.map((r, i) => (
              <span
                key={i}
                className="text-[9px] font-medium px-1.5 py-px rounded bg-[var(--v2-border-subtle)] text-[var(--v2-text-muted)]"
              >
                {r}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
