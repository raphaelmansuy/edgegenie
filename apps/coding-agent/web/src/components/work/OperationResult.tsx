import { ObservedDetails } from "./ObservedDetails";
import { useContext, useState } from "react";
import { SessionIdContext, request, type WorkRow } from "./model";
export function OperationResult({ row }: { row: WorkRow }) {
  const session = useContext(SessionIdContext);
  const [page, setPage] = useState<Record<string, unknown>>();
  const [error, setError] = useState("");
  const data = (page ?? row.result) as
    | {
        columns?: (
          | string
          | {
              name: string;
            }
        )[];
        rows?: unknown[][];
        totalRows?: number;
        nextChunk?: number;
      }
    | undefined;
  const [offset, setOffset] = useState(0);
  if (!data || !Array.isArray(data.rows) || !Array.isArray(data.columns))
    return (
      <>
        <ObservedDetails
          value={(row.result ?? {}) as Record<string, unknown>}
        />
        <details>
          <summary>Full observed record</summary>
          <pre className="work-diff" tabIndex={0}>
            {JSON.stringify(row.result, null, 2)}
          </pre>
        </details>
      </>
    );
  return (
    <>
      <p>
        {data.totalRows === undefined
          ? "Total row count unknown"
          : `${data.totalRows.toLocaleString()} total rows`}
      </p>
      <div
        className="work-table-wrap"
        tabIndex={0}
        role="region"
        aria-label="Observed run rows"
      >
        <table className="work-table">
          <caption className="sr-only">Observed operation result</caption>
          <thead>
            <tr>
              {data.columns.map((c, i) => (
                <th key={i} scope="col">
                  {typeof c === "string" ? c : c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.slice(offset, offset + 200).map((r, i) => (
              <tr key={i}>
                {r.map((v, j) => (
                  <td key={j}>{v === null ? "NULL" : String(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="work-actions">
        {offset > 0 && (
          <button
            className="btn ghost"
            onClick={() => setOffset((n) => Math.max(0, n - 200))}
          >
            Previous rows
          </button>
        )}
        {offset + 200 < data.rows.length && (
          <button
            className="btn ghost"
            onClick={() => setOffset((n) => n + 200)}
          >
            More rows
          </button>
        )}
        {data.nextChunk !== undefined && data.nextChunk !== null && (
          <button
            className="btn ghost"
            onClick={async () => {
              try {
                const result = await request(
                  `/api/sessions/${session}/operations/${row.id}/results?chunk=${data.nextChunk}`,
                );
                setPage(result);
                setOffset(0);
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            Next result chunk
          </button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
    </>
  );
}
