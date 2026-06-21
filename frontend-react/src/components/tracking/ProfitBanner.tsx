/** Big profit banner matching football/tennis design. */

interface ProfitBannerProps {
  title: string;
  value: number;
  suffix?: string;
  secondaryText?: string;
  accentColor?: "green" | "gold" | "auto";
}

export default function ProfitBanner({
  title,
  value,
  suffix = "",
  secondaryText,
  accentColor = "auto",
}: ProfitBannerProps) {
  const isPositive = value > 0;
  const isNegative = value < 0;
  const sign = value >= 0 ? "+" : "";

  const borderLeft =
    accentColor === "green"
      ? "var(--v2-green)"
      : accentColor === "gold"
        ? "var(--v2-gold)"
        : isPositive
          ? "var(--v2-green)"
          : isNegative
            ? "var(--v2-red)"
            : "var(--v2-text-muted)";

  const valueColor = isPositive
    ? "var(--v2-green)"
    : isNegative
      ? "var(--v2-red)"
      : "var(--v2-text-primary)";

  return (
    <div
      className="rounded-xl p-3 md:p-5 border flex flex-col gap-1"
      style={{
        background: "var(--v2-bg-card)",
        borderColor: "var(--v2-border-subtle)",
        borderLeftWidth: "3px",
        borderLeftColor: borderLeft,
      }}
    >
      <p
        className="text-[10px] uppercase font-semibold"
        style={{ letterSpacing: "1px", color: "var(--v2-text-muted)" }}
      >
        {title}
      </p>
      <p
        className="text-2xl md:text-4xl font-mono font-extrabold leading-none tracking-tight"
        style={{ color: valueColor }}
      >
        {sign}
        {value.toFixed(2)}
        {suffix}
      </p>
      {secondaryText && (
        <p
          className="text-xs font-mono mt-0.5"
          style={{ color: "var(--v2-text-secondary)" }}
        >
          {secondaryText}
        </p>
      )}
    </div>
  );
}
