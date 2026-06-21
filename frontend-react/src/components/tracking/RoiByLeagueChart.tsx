/** Profit / ROI by league bar chart (Recharts) for resolved picks. */
import { useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { leagueLabel, type PickData } from "../../config/constants";

interface RoiByLeagueChartProps {
  picks: PickData[];
  height?: number;
}

interface Row {
  league: string;
  profit: number;
  count: number;
  winRate: number;
}

export default function RoiByLeagueChart({ picks, height = 280 }: RoiByLeagueChartProps) {
  const data = useMemo<Row[]>(() => {
    const byLeague: Record<string, { profit: number; count: number; won: number }> = {};
    for (const p of picks) {
      if (p.result !== "won" && p.result !== "lost") continue;
      const key = leagueLabel(p.match.league);
      if (!byLeague[key]) byLeague[key] = { profit: 0, count: 0, won: 0 };
      byLeague[key].profit += p.profitUnits || 0;
      byLeague[key].count += 1;
      if (p.result === "won") byLeague[key].won += 1;
    }
    return Object.entries(byLeague)
      .map(([league, s]) => ({
        league,
        profit: Math.round(s.profit * 100) / 100,
        count: s.count,
        winRate: s.count > 0 ? Math.round((s.won / s.count) * 100) : 0,
      }))
      .sort((a, b) => b.profit - a.profit);
  }, [picks]);

  const gridColor = "rgba(255,255,255,0.04)";
  const axisColor = "#8b97ad";

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm"
        style={{ height, color: "var(--v2-text-secondary)" }}
      >
        Sin picks resueltos por liga
      </div>
    );
  }

  const CustomTooltip = ({
    active,
    payload,
  }: {
    active?: boolean;
    payload?: Array<{ payload: Row }>;
  }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
      <div
        className="rounded-lg p-2 text-xs border"
        style={{
          background: "var(--v2-bg-card)",
          borderColor: "var(--v2-border-subtle)",
        }}
      >
        <p className="font-semibold" style={{ color: "var(--v2-text-primary)" }}>
          {d.league}
        </p>
        <p style={{ color: d.profit >= 0 ? "var(--v2-green)" : "var(--v2-red)" }}>
          Profit: {d.profit >= 0 ? "+" : ""}
          {d.profit.toFixed(2)}u
        </p>
        <p style={{ color: "var(--v2-text-secondary)" }}>
          {d.count} picks | WR: {d.winRate}%
        </p>
      </div>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
        <XAxis dataKey="league" stroke={axisColor} tick={{ fontSize: 10 }} type="category" />
        <YAxis stroke={axisColor} tick={{ fontSize: 10 }} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
        <Bar dataKey="profit" radius={[4, 4, 0, 0]}>
          {data.map((entry, idx) => (
            <Cell key={idx} fill={entry.profit >= 0 ? "#22c55e" : "#ef4444"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
