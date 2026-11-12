import { useState } from "react";
import type { SqlRun } from "../domain/query";
import { ACTIVE_SQL, sqlStateLabel } from "../domain/query";
import { copyText } from "../domain/clipboard";

export function SqlResults({ run, stale, onCancel, onAcknowledge }: { run: SqlRun | null; stale?: boolean; onCancel?: () => void; onAcknowledge?: () => void }) {
  const [page, setPage] = useState(0);
  const [columnPage, setColumnPage] = useState(0);
  const [copied, setCopied] = useState("");
  const [details, setDetails] = useState(false);
  const data = run?.result;
  const start = page * 200, col = columnPage * 50;
  if (!run) return <section className="sql-result-empty" aria-label="Query results">
    <span className="sql-empty-symbol" aria-hidden>↳</span><h3>Your results will appear here</h3>
    <p>Choose a warehouse, review your SQL, then run the query.</p>
    <span className="sql-shortcut"><kbd>⌘</kbd> <kbd>Enter</kbd> <span>Run query or selection</span></span>
  </section>;
  const active = ACTIVE_SQL.has(run.state);
  return <section className="sql-results" aria-label="Query results">
    <div className="sql-result-head">
      <div className="sql-run-label"><span className={`sql-status-dot is-${run.state}`} aria-hidden />
        <strong role="status">{sqlStateLabel(run.state)}</strong>
        {data && <span>{data.rowCount.toLocaleString()} {data.rowCount===1?"row":"rows"} returned{data.truncated ? " · Preview truncated" : ""}</span>}
        {run.finishedAt && <span>{Math.max(0,run.finishedAt-run.createdAt).toFixed(1)}s</span>}
      </div>
      <div className="sql-inline-actions">
        {active && onCancel && run.state !== "submission_unknown" && <button className="btn" onClick={onCancel}>Cancel run</button>}
        <button className="btn ghost" aria-expanded={details} onClick={() => setDetails(!details)}>Run details</button>
      </div>
    </div>
    {stale && <p className="sql-callout">Source or execution inputs changed since this run. These results belong to the previous snapshot.</p>}
    {run.error && <p className="sql-callout is-error" role="alert">{run.error}</p>}
    {run.state === "submission_unknown" && <p className="sql-callout" role="alert">We could not confirm whether this run started. Check native query history before running again. This operation will not be automatically replayed. {onAcknowledge&&<button className="btn" onClick={onAcknowledge}>Acknowledge outcome unknown</button>}</p>}
    {run.state === "outcome_unknown" && <p className="sql-callout">You acknowledged an unresolved run. It may still have executed. A new Run action is a separate execution.</p>}
    {run.resultExpired && <p className="sql-callout">This run succeeded, but its results have expired. A new Run action executes a new query.</p>}
    {details && <details className="sql-provenance" open><summary>Execution snapshot</summary>
      <dl><dt>Run</dt><dd>{run.id}</dd><dt>Warehouse</dt><dd>{run.warehouseId}</dd>
        <dt>Started</dt><dd>{new Date(run.createdAt*1000).toLocaleString()}</dd><dt>Source hash</dt><dd>{run.sourceHash}</dd>
        <dt>Parameters</dt><dd>{run.parameterNames?.join(", ") || "None"} · values excluded from history</dd></dl>
      <pre>{run.text || "Source snapshot unavailable"}</pre>
    </details>}
    {data && <>
      <div className="sql-table-scroll" tabIndex={0} aria-label="Scrollable query result table">
        <table className="sql-result-table"><caption className="sr-only">Result preview for {run.name}, run {run.id}</caption>
          <thead><tr><th scope="col" className="sql-row-number">#</th>{data.columns.slice(col,col+50).map((c,i) => <th scope="col" key={col+i}>{c.name}<small>{c.type_text || "value"}</small></th>)}</tr></thead>
          <tbody>{data.rows.slice(start,start+200).map((row,i) => <tr key={start+i}><th scope="row" className="sql-row-number">{start+i+1}</th>{row.slice(col,col+50).map((v,j) => <td key={col+j}>{v===null ? <span className="sql-null">NULL</span> : v==="" ? <span className="sql-null">empty string</span> : v}</td>)}</tr>)}</tbody>
        </table>
        {!data.rows.length && <p className="sql-no-rows">Query succeeded. No rows were returned.</p>}
      </div>
      <div className="sql-table-footer"><span>Preview · up to 1,000 rows / 4 MiB</span><div className="sql-inline-actions">
        {data.rows.length>200 && <><button className="btn" disabled={page===0} onClick={() => setPage(p=>p-1)}>Previous rows</button><span>{start+1}–{Math.min(start+200,data.rows.length)}</span><button className="btn" disabled={start+200>=data.rows.length} onClick={() => setPage(p=>p+1)}>Next rows</button></>}
        {data.columns.length>50 && <><button className="btn" disabled={!columnPage} onClick={() => setColumnPage(p=>p-1)}>Previous columns</button><button className="btn" disabled={col+50>=data.columns.length} onClick={() => setColumnPage(p=>p+1)}>Next columns</button></>}
        <button className="btn ghost" onClick={async () => { const rows=data.rows.slice(start,start+200); setCopied(await copyText([data.columns.slice(col,col+50).map(c=>c.name),...rows.map(r=>r.slice(col,col+50).map(v=>v===null?"NULL":v))].map(r=>r.join("\t")).join("\n")) ? "Copied visible rows" : "Clipboard unavailable"); }}>Copy visible rows</button>
      </div><span role="status">{copied}</span></div>
    </>}
    {!data && active && run.state!=="submission_unknown" && <p className="sql-waiting"><span className="spin" /> {run.cancelRequested ? "Waiting for the warehouse to confirm cancellation…" : "The warehouse is processing this run. You can keep editing or return later."}</p>}
  </section>;
}
