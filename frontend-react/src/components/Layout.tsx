/** Top nav bar layout with dark premium theme. */
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard" },
  { to: "/picks", label: "Picks" },
  { to: "/tracking", label: "Tracking" },
  { to: "/standings", label: "Clasificación" },
];

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false);

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      isActive
        ? "bg-[var(--v2-bg-elevated)] text-[var(--v2-gold)]"
        : "text-[var(--v2-text-secondary)] hover:bg-[var(--v2-bg-elevated)] hover:text-[var(--v2-text-primary)]"
    }`;

  return (
    <div className="min-h-screen flex flex-col bg-[var(--v2-bg-app)]">
      {/* Top nav */}
      <header className="sticky top-0 z-30 border-b border-[var(--v2-border-subtle)] bg-[var(--v2-bg-card)]/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
          {/* Branding */}
          <NavLink to="/" className="flex items-center gap-2">
            <span className="text-xl" role="img" aria-label="basketball">
              🏀
            </span>
            <span className="text-base font-bold tracking-tight text-[var(--v2-text-primary)]">
              SmartOdds <span className="text-[var(--v2-gold)]">Básquet</span>
            </span>
          </NavLink>

          {/* Desktop nav */}
          <nav className="ml-6 hidden items-center gap-1 md:flex">
            {NAV_ITEMS.map(({ to, label }) => (
              <NavLink key={to} to={to} end={to === "/"} className={linkClass}>
                {label}
              </NavLink>
            ))}
          </nav>

          <span className="ml-auto hidden text-[11px] font-medium uppercase tracking-wider text-[var(--v2-text-muted)] sm:inline">
            NBA · WNBA · NCAAB · EuroLeague
          </span>

          {/* Mobile menu button */}
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="ml-auto rounded-md p-1.5 text-[var(--v2-text-secondary)] hover:bg-[var(--v2-bg-elevated)] hover:text-[var(--v2-text-primary)] md:hidden"
            aria-label="Menu"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>

        {/* Mobile nav */}
        {menuOpen && (
          <nav className="flex flex-col gap-1 border-t border-[var(--v2-border-subtle)] px-4 py-2 md:hidden">
            {NAV_ITEMS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                onClick={() => setMenuOpen(false)}
                className={linkClass}
              >
                {label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      {/* Page content */}
      <main className="mx-auto w-full max-w-7xl flex-1 p-4 sm:p-6">
        <Outlet />
      </main>
    </div>
  );
}
