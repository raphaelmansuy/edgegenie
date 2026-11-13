/** The notebook's own toolbar: run everything, stop, clear, and where cells run.
 *
 * Databricks puts `Run all` and the compute picker on the notebook, not on a cell, because "run the
 * whole thing" is the most common thing you do to a notebook. Ours runs the SQL cells in order and
 * stops at the first failure (the same rule as Databricks), and says up front which cells it will not
 * run and why, so a skipped Python cell is a stated fact and not a silent gap.
 *
 * There is no cluster picker: SQL runs on a serverless SQL warehouse as the signed-in user, and the
 * bar says which one once it has run. A control for a choice the app does not offer would be a lie.
 */
import { useEffect, useRef, useState } from "react";
import { runAllLabel, type CellRun, type RunPlan } from "../domain/cellrun";
import { chipFor, type SessionStatus } from "../domain/session";
import { Close, PlayAll, Stop } from "./Icons";

/** The notebook's Python session: a chip that says what state it is in, and a small menu to restart or
 *  stop it. Variables live in it, and it costs compute while it is up, so both controls are one click. */
function SessionChip({ status, fallback, onRestart, onStop }: {
  status: SessionStatus; fallback: string | null; onRestart: () => void; onStop: () => void;
}) {
  const chip = chipFor(status, fallback);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <span className="nb-session" ref={box}>
      <button type="button" className={`nb-bar-compute nb-session-chip is-${chip.tone}`} aria-expanded={open}
        aria-haspopup="menu" onClick={() => setOpen((o) => !o)} title={chip.title}>
        <span className="nb-bar-dot" aria-hidden />
        {chip.label}
      </button>
      {open && (
        <div className="nb-session-pop" role="menu" aria-label="Python session">
          <p className="nb-session-note">{chip.title}</p>
          <button type="button" role="menuitem" className="btn sm ghost" disabled={!chip.canRestart}
            onClick={() => { setOpen(false); onRestart(); }}>Restart session</button>
          <button type="button" role="menuitem" className="btn sm ghost" disabled={!chip.canStop}
            onClick={() => { setOpen(false); onStop(); }}>Stop session</button>
        </div>
      )}
    </span>
  );
}

export function NotebookBar({ plan, runs, runningAll, batch, session, onRunAll, onStop, onClear }: {
  /** Present when the app can keep a Python session; absent means one-shot runs only. */
  session?: { status: SessionStatus; fallback: string | null; onRestart: () => void; onStop: () => void };
  plan: RunPlan;
  runs: Record<string, CellRun>;
  runningAll: boolean;
  /** The cells this run is walking, when it is a span rather than the whole notebook. */
  batch?: readonly string[] | null;
  onRunAll: () => void;
  onStop: () => void;
  onClear: () => void;
}) {
  const hasOutputs = Object.keys(runs).length > 0;
  const warehouse = Object.values(runs).map((r) => r.warehouse).filter(Boolean).at(-1);
  const label = runAllLabel(plan, runs, runningAll, batch);
  const skipped = plan.skipped.map((s) => `cell ${s.index + 1}: ${s.reason}`).join("\n");
  return (
    <div className="nb-bar" role="toolbar" aria-label="Notebook">
      {runningAll ? (
        <button type="button" className="btn sm stop" onClick={onStop} aria-label="Stop running the notebook">
          <Stop size={12} /> Stop
        </button>
      ) : (
        <button type="button" className="btn sm primary" onClick={onRunAll} disabled={plan.runnable.length === 0}
          title={plan.runnable.length ? (plan.python.length
            ? (session && !session.fallback
            ? "Run every cell in order. SQL runs on a warehouse as you; Python runs in this notebook's session as the app"
            : "Run every cell. SQL runs in order on a warehouse as you; Python runs as one serverless job as the app")
            : "Run every SQL cell in order; stops at the first failure") : (plan.skipped[0]?.reason ?? "No cell here can run in the app")}>
          <PlayAll size={13} /> Run all
        </button>
      )}
      <span className="nb-bar-status" role="status" title={skipped || undefined}>{label}</span>
      <span className="nb-bar-end">
        <span className={`nb-bar-compute${warehouse ? " is-connected" : ""}`} title={warehouse ? "Warehouse used by the last run" : "SQL execution target; availability is checked when you run a cell"}>
          <span className="nb-bar-dot" aria-hidden />
          {warehouse && !plan.python.length ? warehouse : "Serverless SQL"}
        </span>
        {plan.python.length > 0 && (
          <span className="nb-bar-compute is-app"
            title="Python cells run on serverless compute as the app's service principal, not as you. They run together as one job, so cells share variables.">
            <span className="nb-bar-dot" aria-hidden />
            Python · as the app
          </span>
        )}
        {plan.python.length > 0 && session && (
          <SessionChip status={session.status} fallback={session.fallback}
            onRestart={session.onRestart} onStop={session.onStop} />
        )}
        {hasOutputs && !runningAll && (
          <button type="button" className="btn sm ghost" onClick={onClear} title="Clear every output">
            <Close size={11} /> Clear outputs
          </button>
        )}
      </span>
    </div>
  );
}
