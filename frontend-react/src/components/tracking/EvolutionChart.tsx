/** Cumulative profit evolution chart (Recharts AreaChart) for resolved picks. */
import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { formatBetType, type PickData } from "../../config/constants";

interface EvolutionChartProps {
  picks: PickData[];
  height?: number;
}

interface Point {
  index: number;
  profit: number;
  label: string;
  result: string;
  bet: string;
  odds: string;
}

export default function EvolutionChart({ picks, height = 300 }: EvolutionChartProps) {
  const data = useMemo<Point[]>(() => {
    const resolved = picks
      .filter((p) => p.result === "won" || p.result === "lost")
      .sort((a, b) =>
        (a.createdAt || "").localeCompare(b.createdAt || ""),
      );

    let cum = 0;
    return resolved.map((p, i) => {
      cum += p.profitUnits || 0;
      return {
        index: i + 1,
        profit: Math.round(cum * 100) / 100,
        label: `${p.match.homeTeam} vs ${p.match.awayTeam}`,
        result: p.result === "won" ? "W" : "L",
        bet: formatBetType(p.betType, p.match),
        odds: (p.bestOdds ?? 0).toFixed(2),
      };
    });
  }, [picks]);

  const gridColor = "rgba(255,255,255,0.04)";
  const axisColor = "#8b97ad";
  const refLine = "#555";

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm"
        style={{ height, color: "var(--v2-text-secondary)" }}
      >
        Sin datos resueltos para graficar
      </div>
    );
  }

  const CustomTooltip = ({
    active,
    payload,
  }: {
    active?: boolean;
    payload?: Array<{ value?: number; payload: Point }>;
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
        <span className="font-bold" style={{ color: "var(--v2-gold)" }}>
          {(payload[0].value ?? 0).toFixed(2)}u
        </span>
        <p style={{ color: "var(--v2-text-secondary)" }}>
          {d.result} {d.label} | {d.bet} @ {d.odds}
        </p>
      </div>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
        <XAxis
          dataKey="index"
          stroke={axisColor}
          tick={{ fontSize: 10 }}
          tickLine={false}
        />
        <YAxis
          stroke={axisColor}
          tick={{ fontSize: 10 }}
          tickLine={false}
          label={{
            value: "Profit (u)",
            angle: -90,
            position: "insideLeft",
            fill: axisColor,
            fontSize: 11,
          }}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={0} stroke={refLine} strokeDasharray="3 3" />
        <Area
          type="monotone"
          dataKey="profit"
          name="Profit acumulado"
          stroke="#fbbf24"
          fill="rgba(212,175,55,0.1)"
          strokeWidth={2.5}
          dot={false}
          connectNulls
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
