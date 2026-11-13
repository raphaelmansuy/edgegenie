import type { AgentNotice, Compaction } from "../domain/agentupdates";
function Content({block}: {block: unknown}) {
  if (!block || typeof block !== "object") return <p>Unsupported summary content.</p>;
  const value = block as Record<string, unknown>;
  if (value.type === "text") return <p className="agent-update-text">{String(value.text ?? "")}</p>;
  return <details><summary>Non-text summary content</summary><pre>{JSON.stringify(block, null, 2)}</pre></details>;
}
export function AgentUpdates({notices = [], compactions = []}: {notices?: AgentNotice[]; compactions?: Compaction[]}) {
  if (!notices.length && !compactions.length) return null;
  return <section className="agent-updates" aria-label="Agent updates" tabIndex={0}>
    {notices.slice(-3).map((notice, i) => <div className="agent-update" role={notice.severity === "error" ? "alert" : "status"} key={i}>
      <strong>{notice.text}</strong>{notice.description && <p>{notice.description}</p>}
    </div>)}
    {compactions.slice(-3).map(row => <details className="agent-update" key={row.id}>
      <summary>Context compaction · {row.status.replaceAll("_", " ")}</summary>
      {row.summary.length ? row.summary.map((block, i) => <Content key={i} block={block} />) : <p>No summary was supplied.</p>}
      {row.truncated && <p>Summary display limit reached.</p>}
      {row.error && <p role="alert">{row.error}</p>}
    </details>)}
  </section>;
}
