/** Centered loading spinner matching the dark theme. */
export default function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-16 text-[var(--v2-text-muted)]">
      <svg
        className="w-8 h-8 mr-3 animate-spin"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
      <span className="text-sm">Cargando…</span>
    </div>
  );
}
