/** Colored league badge (basketball analog of tennis SurfaceBadge). */
import { leagueLabel, leagueColor } from "../config/constants";

interface LeagueBadgeProps {
  league?: string | null;
  tier?: string | null;
}

export default function LeagueBadge({ league, tier }: LeagueBadgeProps) {
  const color = leagueColor(league);
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md px-2 py-[2px] text-[10px] font-bold uppercase tracking-wide flex-shrink-0"
      style={{
        color,
        background: `${color}1f`,
        border: `1px solid ${color}40`,
      }}
    >
      {leagueLabel(league)}
      {tier && (
        <span className="text-[9px] font-semibold opacity-70">{tier}</span>
      )}
    </span>
  );
}
