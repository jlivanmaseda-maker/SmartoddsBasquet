/** Calibration-phase banner: all leagues in SHADOW, no live signals yet. */
export default function CalibrationBanner() {
  return (
    <div
      className="rounded-xl border px-4 py-3 flex items-start gap-3 text-sm"
      style={{
        background: "var(--v2-gold-dim)",
        borderColor: "rgba(251,191,36,0.3)",
      }}
    >
      <span className="text-base leading-none mt-0.5">🟡</span>
      <p style={{ color: "var(--v2-text-secondary)" }}>
        <b style={{ color: "var(--v2-gold)" }}>Fase de calibración</b> — todas las
        ligas en <b style={{ color: "var(--v2-gold)" }}>SHADOW</b>. Los picks se
        registran para el backtest pero todavía no se emiten señales en vivo hasta
        validar la rentabilidad.
      </p>
    </div>
  );
}
