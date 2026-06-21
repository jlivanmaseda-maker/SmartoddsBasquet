/** Reusable stat card for dashboards and tracking grids. */

interface StatCardProps {
  label: string;
  value: string | number;
  suffix?: string;
  color?: "green" | "red" | "gold" | "blue" | "default";
  subtitle?: string;
}

const COLOR_MAP: Record<string, string> = {
  green: "text-[var(--v2-green)]",
  red: "text-[var(--v2-red)]",
  gold: "text-[var(--v2-gold)]",
  blue: "text-blue-400",
  default: "text-[var(--v2-text-primary)]",
};

export default function StatCard({
  label,
  value,
  suffix,
  color = "default",
  subtitle,
}: StatCardProps) {
  const valueColor = COLOR_MAP[color] || COLOR_MAP.default;

  return (
    <div className="rounded-xl border border-[var(--v2-border-subtle)] bg-[var(--v2-bg-card)] px-4 py-3">
      <p className="mb-1 text-xs font-medium uppercase tracking-wider text-[var(--v2-text-muted)]">
        {label}
      </p>
      <p className={`text-2xl font-bold leading-tight ${valueColor}`}>
        {value}
        {suffix && (
          <span className="ml-1 text-sm font-normal text-[var(--v2-text-secondary)]">
            {suffix}
          </span>
        )}
      </p>
      {subtitle && (
        <p className="mt-0.5 text-xs text-[var(--v2-text-secondary)]">
          {subtitle}
        </p>
      )}
    </div>
  );
}

export type { StatCardProps };
