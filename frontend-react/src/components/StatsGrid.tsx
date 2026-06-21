/** Football/tennis-style stat grid (item list with gold check icons). */

function CheckIcon() {
  return (
    <svg
      className="h-4 w-4 flex-shrink-0"
      style={{ color: "var(--v2-gold)" }}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2.5}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

export interface StatItem {
  label: string;
  value: string | number;
  color?: "green" | "red" | "gold" | "blue" | "default";
}

interface StatsGridProps {
  items: StatItem[];
  columns?: 2 | 3;
  title?: string;
}

const COLOR_MAP: Record<string, string> = {
  green: "text-[var(--v2-green)]",
  red: "text-[var(--v2-red)]",
  gold: "text-[var(--v2-gold)]",
  blue: "text-blue-400",
  default: "text-[var(--v2-text-primary)]",
};

export default function StatsGrid({ items, columns = 2, title }: StatsGridProps) {
  return (
    <div
      className="rounded-xl p-3 md:p-5 border"
      style={{
        background: "var(--v2-bg-card)",
        borderColor: "var(--v2-border-subtle)",
      }}
    >
      {title && (
        <h3
          className="text-sm font-medium mb-4"
          style={{ color: "var(--v2-text-primary)" }}
        >
          {title}
        </h3>
      )}
      <div
        className={`grid gap-y-3 gap-x-4 md:gap-x-8 ${
          columns === 3 ? "grid-cols-2 md:grid-cols-3" : "grid-cols-2"
        }`}
      >
        {items.map((item, idx) => (
          <div key={idx} className="flex items-center gap-2">
            <CheckIcon />
            <span className="text-sm" style={{ color: "var(--v2-text-secondary)" }}>
              {item.label}:
            </span>
            <span
              className={`text-sm font-mono font-semibold ${
                COLOR_MAP[item.color || "default"]
              }`}
            >
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
