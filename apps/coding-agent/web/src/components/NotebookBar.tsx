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
import { runAllLabel, type CellRun, type RunPlan } from "../domain/cellrun";
import { Close, PlayAll, Stop } from "./Icons";

export function NotebookBar({ plan, runs, runningAll, onRunAll, onStop, onClear }: {
  plan: RunPlan;
  runs: Record<string, CellRun>;
  runningAll: boolean;
  onRunAll: () => void;
  onStop: () => void;
  onClear: () => void;
}) {
  const hasOutputs = Object.keys(runs).length > 0;
  const warehouse = Object.values(runs).map((r) => r.warehouse).filter(Boolean).at(-1);
  const label = runAllLabel(plan, runs, runningAll);
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
            ? "Run every cell. SQL runs in order on a warehouse as you; Python runs as one serverless job as the app"
            : "Run every SQL cell in order; stops at the first failure") : (plan.skipped[0]?.reason ?? "No cell here can run in the app")}>
          <PlayAll size={13} /> Run all
        </button>
      )}
      <span className="nb-bar-status" role="status" title={skipped || undefined}>{label}</span>
      <span className="nb-bar-spacer" />
      <span className="nb-bar-compute" title="SQL cells run on a serverless SQL warehouse, as you">
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
      {hasOutputs && !runningAll && (
        <button type="button" className="btn sm ghost" onClick={onClear} title="Clear every output">
          <Close size={11} /> Clear outputs
        </button>
      )}
    </div>
  );
}
