/**
 * Picks · la sombra por regla y mercado (25-oct-2026).
 *
 * Mismo diseño que el apartado Sombra del TT: arriba el estado del sistema, luego cada regla en prueba con sus
 * resultados (a la cuota cogida y a la mediana de las casas blandas, con su error, el CLV contra el cierre de
 * Pinnacle y, en hándicap y total, los puntos de línea frente al cierre) y debajo las tarjetas de los picks.
 * Umbral para publicar una regla: 300 picks liquidados y ROI a mediana menos 2 errores por encima de cero.
 */
import { useMemo, useState } from "react";
import { useQuery } from "../hooks/useQuery";
import { SHADOW_PICKS_QUERY, SHADOW_RULES_QUERY } from "../config/queries";
import { leagueLabel } from "../config/constants";
import LeagueBadge from "../components/LeagueBadge";
import LoadingSpinner from "../components/LoadingSpinner";

interface Regla {
  clave: string;
  regla: string;
  mercado: string;
  nombre: string;
  descripcion: string;
  desde: string | null;
  picks: number;
  abiertos: number;
  liquidados: number;
  ganados: number;
  nulos: number;
  unidades: number;
  roi: number | null;
  roiError: number | null;
  roiMediana: number | null;
  roiMedianaError: number | null;
  nMediana: number;
  clv: number | null;
  clvPositivos: number | null;
  nClv: number;
  lineaVsCierre: number | null;
  nLinea: number;
  cuotaMedia: number | null;
  objetivo: number;
  cumpleUmbral: boolean;
}

interface EstadoSistema {
  version: string;
  reglaGanador: string;
  reglaLineas: string;
  lineasActivas: boolean;
  vigilanteOk: boolean | null;
  vigilanteFallos: string[];
  vigilanteActualizado: string | null;
  creditosRestantes: number | null;
}

interface Casa {
  casa: string;
  cuota: number;
}

interface PickSombra {
  id: number;
  clave: string;
  reglaNombre: string;
  mercado: string;
  liga: string | null;
  inicio: string | null;
  creado: string | null;
  horasAntes: number | null;
  local: string;
  visitante: string;
  seleccion: string;
  cuota: number | null;
  casa: string | null;
  cuotaMediana: number | null;
  nCasas: number | null;
  cuotaMinima: number | null;
  pinnacleJusta: number | null;
  edge: number | null;
  estado: string;
  beneficio: number | null;
  clv: number | null;
  cuotaCierreJusta: number | null;
  lineaVsCierre: number | null;
  marcador: string | null;
  casas: Casa[];
}

const PERIODOS = [
  { dias: 7, label: "7 días" },
  { dias: 14, label: "14 días" },
  { dias: 30, label: "30 días" },
  { dias: 0, label: "Todo" },
];

const ESTADOS = [
  { key: "abiertos", label: "Abiertos" },
  { key: "liquidados", label: "Liquidados" },
  { key: "todos", label: "Todos" },
];

const ESTADO_TXT: Record<string, { txt: string; cls: string }> = {
  abierto: { txt: "Abierto", cls: "bg-[#f59e0b]/15 text-[#f59e0b]" },
  ganado: { txt: "Ganado", cls: "bg-[var(--v2-green)]/15 text-[var(--v2-green)]" },
  perdido: { txt: "Perdido", cls: "bg-[var(--v2-red)]/15 text-[var(--v2-red)]" },
  nulo: { txt: "Nulo", cls: "bg-[var(--v2-bg-elevated)] text-[var(--v2-text-muted)]" },
};

/** Las fechas del servidor vienen en UTC sin zona: se les añade para que el navegador las pase a hora de España. */
function fecha(iso: string | null): Date | null {
  if (!iso) return null;
  const conZona = /Z$|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const d = new Date(conZona);
  return Number.isNaN(d.getTime()) ? null : d;
}

function hora(iso: string | null): string {
  const d = fecha(iso);
  if (!d) return "—";
  return d.toLocaleString("es-ES", {
    timeZone: "Europe/Madrid", weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function dia(iso: string | null): string {
  const d = fecha(iso);
  if (!d) return "—";
  return d.toLocaleDateString("es-ES", { timeZone: "Europe/Madrid", day: "numeric", month: "short" });
}

function haceMinutos(iso: string | null): string {
  const d = fecha(iso);
  if (!d) return "";
  const min = Math.round((Date.now() - d.getTime()) / 60000);
  if (min < 1) return "ahora mismo";
  if (min < 120) return `hace ${min} min`;
  return `hace ${Math.round(min / 60)} h`;
}

function num(v: number | null | undefined, dec = 1, suf = "", signo = false): string {
  if (v === null || v === undefined) return "—";
  return `${signo && v > 0 ? "+" : ""}${v.toFixed(dec)}${suf}`;
}

function colorValor(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-[var(--v2-text-muted)]";
  return v > 0 ? "text-[var(--v2-green)]" : v < 0 ? "text-[var(--v2-red)]" : "text-[var(--v2-text-secondary)]";
}

/** ROI con su margen de error: verde o rojo solo cuando el signo se sostiene a 2 errores. */
function Roi({ v, e }: { v: number | null; e: number | null }) {
  if (v === null) return <span className="text-[var(--v2-text-muted)]">—</span>;
  const claro = e !== null && Math.abs(v) > e;
  const color = !claro ? "text-[var(--v2-text-secondary)]" : v > 0 ? "text-[var(--v2-green)]" : "text-[var(--v2-red)]";
  return (
    <span className={`font-mono ${color}`}>
      {num(v, 1, " %", true)}
      {e !== null && <span className="text-[var(--v2-text-muted)]"> ± {e.toFixed(0)}</span>}
    </span>
  );
}

export default function PicksPage() {
  const [dias, setDias] = useState(0);
  const [clave, setClave] = useState("");
  const [estado, setEstado] = useState("abiertos");
  const [liga, setLiga] = useState("");

  const diasVar = dias === 0 ? null : dias;
  const reglasQ = useQuery<{ shadowRules: Regla[]; systemStatus: EstadoSistema }>(SHADOW_RULES_QUERY, {
    variables: { dias: diasVar },
    pollInterval: 60000,
  });
  const picksQ = useQuery<{ shadowPicks: PickSombra[] }>(SHADOW_PICKS_QUERY, {
    variables: {
      dias: diasVar,
      clave: clave || null,
      estado: estado === "todos" ? null : estado,
      limit: 400,
    },
    pollInterval: 60000,
  });

  const reglas = reglasQ.data?.shadowRules ?? [];
  const sistema = reglasQ.data?.systemStatus ?? null;
  const todos = useMemo(() => picksQ.data?.shadowPicks ?? [], [picksQ.data]);
  const ligas = useMemo(
    () => Array.from(new Set(todos.map((p) => p.liga).filter((l): l is string => !!l))).sort(),
    [todos],
  );
  const picks = useMemo(() => (liga ? todos.filter((p) => p.liga === liga) : todos), [todos, liga]);

  const error = reglasQ.error || picksQ.error;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-mono text-[18px] font-bold tracking-tight text-[var(--v2-text-hero)] md:text-[22px]">
          Picks · reglas en sombra
        </h1>
        <p className="mt-1 max-w-4xl text-xs text-[var(--v2-text-muted)]">
          Todos los picks están en sombra: se registran y se miden, pero no se publican ni se apuestan. Cada regla se
          mide aparte desde el día en que empezó, a la cuota cogida y a la mediana de las casas blandas, que es lo que
          de verdad se podría conseguir. Cuota mínima = la que todavía da el valor de la regla; ✓ = esa casa la paga
          ahora.
        </p>
      </div>

      {sistema && <EstadoSistemaBar s={sistema} />}

      {error && (
        <div className="rounded-lg border border-[var(--v2-red)]/30 bg-[var(--v2-red-dim)] p-4 text-sm text-[var(--v2-red)]">
          No se pudo cargar la sombra: {error}
        </div>
      )}

      {/* Periodo */}
      <div className="flex flex-wrap gap-2">
        {PERIODOS.map((p) => (
          <button
            key={p.dias}
            onClick={() => setDias(p.dias)}
            className={`rounded-md px-3 py-1 text-xs font-medium ${
              dias === p.dias
                ? "border border-[var(--v2-border-medium)] bg-[var(--v2-bg-elevated)] text-[var(--v2-gold)]"
                : "text-[var(--v2-text-muted)] hover:text-[var(--v2-text-primary)]"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Resumen por regla y mercado */}
      <div className="overflow-x-auto rounded-xl border border-[var(--v2-border-subtle)] bg-[var(--v2-bg-card)]">
        {reglasQ.loading && !reglas.length ? (
          <LoadingSpinner />
        ) : (
          <table className="w-full min-w-[980px] text-left text-xs">
            <thead className="text-[var(--v2-text-muted)]">
              <tr className="border-b border-[var(--v2-border-subtle)]">
                <th className="px-3 py-2">Regla</th>
                <th className="px-2 py-2 text-right">Picks</th>
                <th className="px-2 py-2 text-right">Abiertos</th>
                <th className="px-2 py-2 text-right">Acierto</th>
                <th className="px-2 py-2 text-right">Unidades</th>
                <th className="px-2 py-2 text-right" title="Apostando 1 unidad a la mejor cuota encontrada">ROI cogida ± 2 err.</th>
                <th className="px-2 py-2 text-right" title="Apostando 1 unidad a la mediana de las casas blandas: lo que cuenta para publicar">ROI mediana ± 2 err.</th>
                <th className="px-2 py-2 text-right" title="Cuota cogida frente a la cuota justa de Pinnacle al cierre; entre paréntesis, % de picks con CLV positivo">CLV</th>
                <th className="px-2 py-2 text-right" title="Puntos de línea ganados frente a la línea de Pinnacle al cierre (hándicap y total)">Línea vs cierre</th>
                <th className="px-2 py-2 text-right">Cuota media</th>
                <th className="px-3 py-2" title="300 picks liquidados y ROI a mediana menos 2 errores por encima de cero">Hacia el umbral</th>
              </tr>
            </thead>
            <tbody>
              {reglas.map((r) => (
                <tr
                  key={r.clave}
                  title={r.descripcion}
                  onClick={() => setClave(clave === r.clave ? "" : r.clave)}
                  className={`cursor-pointer border-b border-[var(--v2-border-subtle)] last:border-0 hover:bg-[var(--v2-bg-elevated)] ${
                    clave === r.clave ? "bg-[var(--v2-bg-elevated)]" : ""
                  } ${r.regla === "sharp-v1" ? "opacity-60" : ""}`}
                >
                  <td className="px-3 py-2">
                    <div className="font-medium text-[var(--v2-text-primary)]">{r.nombre}</div>
                    <div className="max-w-[340px] text-[10px] text-[var(--v2-text-muted)]">
                      {r.descripcion} {r.desde ? `Primer pick: ${dia(r.desde)}.` : ""}
                    </div>
                  </td>
                  <td className="px-2 py-2 text-right font-mono">{r.picks}</td>
                  <td className="px-2 py-2 text-right font-mono">{r.abiertos}</td>
                  <td className="px-2 py-2 text-right font-mono whitespace-nowrap">
                    {r.liquidados ? `${((100 * r.ganados) / r.liquidados).toFixed(0)} %` : "—"}
                    <span className="text-[var(--v2-text-muted)]"> ({r.liquidados})</span>
                  </td>
                  <td className={`px-2 py-2 text-right font-mono ${colorValor(r.unidades)}`}>{num(r.unidades, 2, "", true)}</td>
                  <td className="px-2 py-2 text-right whitespace-nowrap"><Roi v={r.roi} e={r.roiError} /></td>
                  <td className="px-2 py-2 text-right whitespace-nowrap"><Roi v={r.roiMediana} e={r.roiMedianaError} /></td>
                  <td className={`px-2 py-2 text-right font-mono whitespace-nowrap ${colorValor(r.clv)}`}>
                    {num(r.clv, 1, " %", true)}
                    {r.clvPositivos !== null && <span className="text-[var(--v2-text-muted)]"> ({r.clvPositivos.toFixed(0)} %)</span>}
                  </td>
                  <td className={`px-2 py-2 text-right font-mono whitespace-nowrap ${colorValor(r.lineaVsCierre)}`}>
                    {r.lineaVsCierre !== null ? `${num(r.lineaVsCierre, 2, "", true)} pts` : "—"}
                  </td>
                  <td className="px-2 py-2 text-right font-mono">{r.cuotaMedia?.toFixed(2) ?? "—"}</td>
                  <td className="px-3 py-2">
                    <Progreso r={r} />
                  </td>
                </tr>
              ))}
              {!reglas.length && (
                <tr>
                  <td colSpan={11} className="px-3 py-6 text-center text-[var(--v2-text-muted)]">
                    No hay picks en este periodo.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
      <p className="text-[10px] text-[var(--v2-text-muted)]">
        Con menos de unos 100 picks liquidados el ROI de una regla todavía no dice nada: mira el ± error. Lo primero que
        indica si una regla funciona es el CLV (coger mejor precio que el cierre de Pinnacle) y, en hándicap y total, los
        puntos de línea frente al cierre. Para publicar una regla hacen falta 300 picks liquidados y que el ROI a
        mediana menos 2 errores quede por encima de cero. Pulsa una fila para ver solo sus picks.
      </p>

      {/* Filtros de la lista */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={clave}
          onChange={(e) => setClave(e.target.value)}
          className="rounded-md border border-[var(--v2-border-medium)] bg-[var(--v2-bg-card)] px-2 py-1 text-xs text-[var(--v2-text-primary)]"
        >
          <option value="">Todas las reglas</option>
          {reglas.map((r) => (
            <option key={r.clave} value={r.clave}>
              {r.nombre}
            </option>
          ))}
        </select>
        <select
          value={liga}
          onChange={(e) => setLiga(e.target.value)}
          className="rounded-md border border-[var(--v2-border-medium)] bg-[var(--v2-bg-card)] px-2 py-1 text-xs text-[var(--v2-text-primary)]"
        >
          <option value="">Todas las ligas</option>
          {ligas.map((l) => (
            <option key={l} value={l}>
              {leagueLabel(l)}
            </option>
          ))}
        </select>
        {ESTADOS.map((e) => (
          <button
            key={e.key}
            onClick={() => setEstado(e.key)}
            className={`rounded-md px-3 py-1 text-xs font-medium ${
              estado === e.key
                ? "border border-[var(--v2-border-medium)] bg-[var(--v2-bg-elevated)] text-[var(--v2-gold)]"
                : "text-[var(--v2-text-muted)] hover:text-[var(--v2-text-primary)]"
            }`}
          >
            {e.label}
          </button>
        ))}
        <span className="text-[10px] text-[var(--v2-text-muted)]">{picks.length} picks · se actualiza cada minuto</span>
      </div>

      {/* Lista de picks */}
      {picksQ.loading && !todos.length ? (
        <LoadingSpinner />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {picks.map((p) => (
            <TarjetaPick key={p.id} p={p} />
          ))}
          {!picks.length && <p className="text-xs text-[var(--v2-text-muted)]">No hay picks con estos filtros.</p>}
        </div>
      )}
    </div>
  );
}

function EstadoSistemaBar({ s }: { s: EstadoSistema }) {
  const ok = s.vigilanteOk;
  return (
    <div className="rounded-xl border border-[var(--v2-border-subtle)] bg-[var(--v2-bg-card)] px-3 py-2.5 text-xs">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
        <span className="flex items-center gap-1.5">
          <span
            className={`h-2 w-2 rounded-full ${
              ok === null ? "bg-[var(--v2-text-muted)]" : ok ? "bg-[var(--v2-green)] shadow-[0_0_6px_var(--v2-green)]" : "bg-[var(--v2-red)] shadow-[0_0_6px_var(--v2-red)]"
            }`}
          />
          <span className="font-medium text-[var(--v2-text-primary)]">
            {ok === null ? "Vigilante sin datos" : ok ? "Vigilante: todo en orden" : `Vigilante: ${s.vigilanteFallos.length} aviso(s)`}
          </span>
          {s.vigilanteActualizado && <span className="text-[var(--v2-text-muted)]">({haceMinutos(s.vigilanteActualizado)})</span>}
        </span>
        <span className="text-[var(--v2-text-secondary)]">
          Reglas: <span className="font-mono text-[var(--v2-text-primary)]">{s.reglaGanador}</span> ganador ·{" "}
          <span className="font-mono text-[var(--v2-text-primary)]">{s.reglaLineas}</span> hándicap y total
          {!s.lineasActivas && <span className="text-[var(--v2-red)]"> (apagada)</span>}
        </span>
        <span className="text-[var(--v2-text-secondary)]">
          Versión <span className="font-mono text-[var(--v2-text-primary)]">{s.version}</span>
        </span>
        <span className="text-[var(--v2-text-secondary)]" title="Cupo de The Odds API, compartido con tenis y fútbol">
          Créditos de cuotas:{" "}
          <span
            className={`font-mono ${
              s.creditosRestantes !== null && s.creditosRestantes < 100000 ? "text-[var(--v2-red)]" : "text-[var(--v2-text-primary)]"
            }`}
          >
            {s.creditosRestantes !== null ? s.creditosRestantes.toLocaleString("es-ES") : "—"}
          </span>
        </span>
      </div>
      {!!s.vigilanteFallos.length && (
        <ul className="mt-2 space-y-0.5 text-[11px] text-[var(--v2-red)]">
          {s.vigilanteFallos.map((f) => (
            <li key={f}>· {f}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Progreso({ r }: { r: Regla }) {
  const pct = Math.min(100, (100 * r.liquidados) / r.objetivo);
  return (
    <div className="w-[130px]">
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--v2-bg-elevated)]">
        <div
          className={`h-full rounded-full ${r.cumpleUmbral ? "bg-[var(--v2-green)]" : "bg-[var(--v2-gold)]"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-1 text-[10px] text-[var(--v2-text-muted)]">
        {r.cumpleUmbral ? (
          <span className="text-[var(--v2-green)]">Cumple el umbral</span>
        ) : r.liquidados >= r.objetivo ? (
          "300 picks, sin ventaja clara"
        ) : (
          `${r.liquidados} de ${r.objetivo} picks`
        )}
      </div>
    </div>
  );
}

function TarjetaPick({ p }: { p: PickSombra }) {
  const est = ESTADO_TXT[p.estado] || ESTADO_TXT.nulo;
  const antes =
    p.horasAntes === null ? "" : p.horasAntes >= 1 ? ` · pick a ${Math.round(p.horasAntes)} h del inicio` : ` · pick a ${Math.round(p.horasAntes * 60)} min del inicio`;
  return (
    <div className="rounded-xl border border-[var(--v2-border-subtle)] bg-[var(--v2-bg-card)] p-3 text-xs">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="truncate text-[10px] font-medium uppercase tracking-wider text-[var(--v2-gold)]">{p.reglaNombre}</span>
        <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${est.cls}`}>{est.txt}</span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-[var(--v2-text-muted)]">
        <LeagueBadge league={p.liga} />
        <span>
          {hora(p.inicio)}
          {antes}
        </span>
      </div>
      <div className="mt-1.5 font-medium text-[var(--v2-text-primary)]">
        {p.local} – {p.visitante}
      </div>
      <div className="mt-1 text-[var(--v2-text-secondary)]">
        Apuesta: <span className="font-semibold text-[var(--v2-text-primary)]">{p.seleccion}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[var(--v2-text-secondary)]">
        <span>
          Cogida <span className="font-mono font-semibold text-[var(--v2-text-primary)]">{num(p.cuota, 2)}</span>
          {p.casa ? ` en ${p.casa}` : ""}
        </span>
        <span>
          Mediana <span className="font-mono">{num(p.cuotaMediana, 2)}</span>
          {p.nCasas ? <span className="text-[var(--v2-text-muted)]"> ({p.nCasas === 1 ? "1 casa" : `${p.nCasas} casas`})</span> : null}
        </span>
        {p.cuotaMinima !== null && (
          <span>
            Mínima <span className="font-mono">{p.cuotaMinima.toFixed(2)}</span>
          </span>
        )}
        {p.pinnacleJusta !== null && (
          <span title="Cuota justa (sin margen) de Pinnacle al crear el pick">
            Pinnacle justa <span className="font-mono">{p.pinnacleJusta.toFixed(2)}</span>
          </span>
        )}
        {p.edge !== null && <span className="text-[var(--v2-green)]">valor {num(p.edge, 1, " %", true)}</span>}
      </div>
      {p.estado === "abierto" ? (
        p.casas.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {p.casas.map((c) => {
              const llega = p.cuotaMinima !== null && c.cuota + 1e-9 >= p.cuotaMinima;
              return (
                <span
                  key={c.casa}
                  className={`rounded border px-1.5 py-0.5 ${
                    llega ? "border-[var(--v2-green)]/40 text-[var(--v2-green)]" : "border-[var(--v2-border-subtle)] text-[var(--v2-text-muted)]"
                  }`}
                >
                  {llega ? "✓ " : ""}
                  {c.casa} {c.cuota.toFixed(2)}
                </span>
              );
            })}
          </div>
        ) : (
          <div className="mt-2 text-[10px] text-[var(--v2-text-muted)]">Ninguna casa blanda ofrece ahora esa misma línea.</div>
        )
      ) : (
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5">
          {p.marcador && <span className="text-[var(--v2-text-secondary)]">Resultado {p.marcador}</span>}
          <span className={colorValor(p.beneficio)}>Beneficio {num(p.beneficio, 2, " u", true)}</span>
          {p.clv !== null && <span className={colorValor(p.clv)}>CLV {num(p.clv, 1, " %", true)}</span>}
          {p.lineaVsCierre !== null && (
            <span className={colorValor(p.lineaVsCierre)}>Línea vs cierre {num(p.lineaVsCierre, 1, " pts", true)}</span>
          )}
        </div>
      )}
    </div>
  );
}
