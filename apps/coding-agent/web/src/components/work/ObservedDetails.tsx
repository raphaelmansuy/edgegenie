/** Native observations render by structure; adding an asset kind does not add a dispatch branch. */
import { Status } from "./Status";
export function ObservedDetails({ value }: { value: Record<string, unknown> }) {
  const nested =
    value.result && typeof value.result === "object"
      ? (value.result as Record<string, unknown>)
      : value;
  const tasks = Array.isArray(nested.tasks)
    ? (nested.tasks as Record<string, unknown>[])
    : [];
  const rows =
    Array.isArray(value.rows) &&
    value.rows.every((r) => r && typeof r === "object" && !Array.isArray(r))
      ? (value.rows as Record<string, unknown>[])
      : [];
  const columns = [...new Set(rows.flatMap(Object.keys))].slice(0, 12);
  const text = (v: unknown) =>
    typeof v === "object" ? JSON.stringify(v) : String(v ?? "");
  return (
    <>
      {value.source ? <p>Source: {String(value.source)}</p> : null}
      {value.grain ? <p>{String(value.grain)}</p> : null}
      {value.lastRefreshedAt ? (
        <p>
          Last refreshed:{" "}
          <time
            dateTime={new Date(
              Number(value.lastRefreshedAt) * 1000,
            ).toISOString()}
          >
            {new Date(Number(value.lastRefreshedAt) * 1000).toLocaleString()}
          </time>
        </p>
      ) : null}
      {tasks.length > 0 && (
        <section aria-label="Task results">
          {tasks.map((task, i) => (
            <article className="work-card" key={String(task.key ?? i)}>
              <header>
                <strong>{String(task.key ?? "Task " + (i + 1))}</strong>
                <Status
                  state={text(
                    (task.state as Record<string, unknown>)?.result_state ??
                      (task.state as Record<string, unknown>)
                        ?.life_cycle_state ??
                      task.state ??
                      "unknown",
                  ).toLowerCase()}
                />
              </header>
              {task.output ? (
                <pre className="work-diff" tabIndex={0}>
                  {JSON.stringify(task.output, null, 2)}
                </pre>
              ) : (
                <p>No task output was reported.</p>
              )}
            </article>
          ))}
        </section>
      )}
      {rows.length > 0 && (
        <div
          className="work-table-wrap"
          role="region"
          aria-label="System-table observations"
          tabIndex={0}
        >
          <table className="work-table">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c} scope="col">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 100).map((r, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c}>{text(r[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {columns.length < new Set(rows.flatMap(Object.keys)).size && (
            <p>Additional fields are available in the full observed record.</p>
          )}
        </div>
      )}
    </>
  );
}
