import { useEffect, useState } from "react";
import { call } from "../api/client";

interface StorageReport {
  sessionId: string;
  journal: { eventRows: number; eventPayloadBytes: number; snapshotPayloadBytes: number };
  ledgers: Record<string, { rows: number; payloadBytes: number }>;
  measurement: string;
  undoRetentionDays: number;
}

/** On-demand diagnostics: opening a conversation never scans its stored payloads. */
export function SessionStorage({ sid }: { sid: string }) {
  const [open, setOpen] = useState(false);
  const [report, setReport] = useState<StorageReport>();
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setReport(undefined); setError("");
    void call<StorageReport>(`/api/sessions/${encodeURIComponent(sid)}/storage`, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setReport(value); })
      .catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Could not load storage report."); });
    return () => controller.abort();
  }, [open, sid, revision]);
  const bytes = (value: number) => `${value.toLocaleString()} bytes`;
  return <details className="session-storage" onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>Session storage</summary>
    {open && <div aria-busy={!report && !error}>
      {!report && !error && <p role="status">Measuring saved history…</p>}
      {error && <p role="alert">{error}</p>}
      {report && <>
        <dl>
          <dt>Journal events</dt><dd>{report.journal.eventRows.toLocaleString()}</dd>
          <dt>Event payloads</dt><dd>{bytes(report.journal.eventPayloadBytes)}</dd>
          <dt>Recovery snapshot</dt><dd>{bytes(report.journal.snapshotPayloadBytes)}</dd>
          <dt>Undo content</dt><dd>{bytes(report.ledgers.previous_content?.payloadBytes ?? 0)}</dd>
          <dt>All ledger payloads</dt><dd>{bytes(Object.values(report.ledgers).reduce((sum, row) => sum + row.payloadBytes, 0))}</dd>
        </dl>
        <p>Undo content is retained for {report.undoRetentionDays} days. Archiving keeps history and workspace resources.</p>
        <p>{report.measurement}</p>
      </>}
      <button className="btn" disabled={!report && !error} onClick={() => setRevision(r => r + 1)}>Refresh storage report</button>
    </div>}
  </details>;
}
