import { useContext, useRef, useState } from "react";
import type { Attachment } from "../../domain/events";
import { AttachAsset, request, type Work } from "./model";
import { ObservedDetails } from "./ObservedDetails";
import { Status } from "./Status";
export function AssetBrowser({
  data,
  session,
}: {
  data: Work;
  session: string;
}) {
  const attach = useContext(AttachAsset);
  const [kind, setKind] = useState(
    data.capabilities.find((c) => c.read)?.kind || "notebook",
  );
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [detail, setDetail] = useState<Record<string, unknown>>();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState("");
  const epoch = useRef(0);
  async function inspect(id: string) {
    const ticket = ++epoch.current;
    setSelected(id);
    setLoading(true);
    setError("");
    try {
      const result = await request(
        `/api/sessions/${session}/assets/${kind}/describe?id=${encodeURIComponent(id)}`,
      );
      if (ticket === epoch.current) setDetail(result);
    } catch (e) {
      if (ticket === epoch.current) setError((e as Error).message);
    } finally {
      if (ticket === epoch.current) setLoading(false);
    }
  }
  return (
    <>
      <form
        className="work-actions"
        onSubmit={async (e) => {
          e.preventDefault();
          const ticket = ++epoch.current;
          setError("");
          setLoading(true);
          try {
            const result = await request(
              `/api/sessions/${session}/assets/${kind}?query=${encodeURIComponent(query)}`,
            );
            if (ticket === epoch.current) {
              setRows(result.items);
              setDetail(undefined);
            }
          } catch (e) {
            if (ticket === epoch.current) setError((e as Error).message);
          } finally {
            if (ticket === epoch.current) setLoading(false);
          }
        }}
      >
        <label>
          Asset kind{" "}
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setRows([]);
              setDetail(undefined);
              epoch.current++;
              setLoading(false);
              setError("");
            }}
          >
            {data.capabilities
              .filter((c) => c.read)
              .map((c) => (
                <option key={c.kind} value={c.kind}>
                  {c.label}
                </option>
              ))}
          </select>
        </label>
        <label>
          Search{" "}
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Name or path"
          />
        </label>
        <button className="btn primary" disabled={loading}>
          Find assets
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      <p className="work-path">Working folder: {data.fence.folder}</p>
      <div className="work-asset-list">
        {rows.map((row, index) => {
          const id = String(row.id ?? row.path ?? "");
          return (
            <article className="work-card" key={id || index}>
              <header>
                {kind}
                {row.capped ? <span>Results capped</span> : null}
              </header>
              <h3>{String(row.name ?? id)}</h3>
              <p className="work-path">{id}</p>
              {row.source ? (
                <p>
                  Source: {String(row.source)} · {String(row.lag ?? "")}
                </p>
              ) : null}
              <div className="work-actions">
                <button
                  className="btn ghost"
                  disabled={loading}
                  onClick={() => void inspect(id)}
                >
                  Inspect asset
                </button>
                <button
                  className="btn ghost"
                  onClick={() =>
                    attach({
                      kind: kind as Attachment["kind"],
                      ref: id,
                      name: String(row.name ?? id),
                    })
                  }
                >
                  Attach to agent
                </button>
              </div>
            </article>
          );
        })}
      </div>
      {loading && <p role="status">Reading as your identity…</p>}
      {detail && (
        <article className="work-card" aria-label="Asset details">
          <header>
            Asset details
            <Status state={String(detail.tier ?? "read")} />
          </header>
          <h3>{selected}</h3>
          {detail.revision ? (
            <p className="work-path">Revision: {String(detail.revision)}</p>
          ) : null}
          {detail.lag ? <p>{String(detail.lag)}</p> : null}
          <ObservedDetails value={detail} />
          <details open={!Array.isArray(detail.rows)}>
            <summary>Definition and observed state</summary>
            <pre className="work-diff" tabIndex={0}>
              {JSON.stringify(detail.definition ?? detail, null, 2)}
            </pre>
          </details>
          <button
            className="btn ghost"
            onClick={() =>
              attach({
                kind: kind as Attachment["kind"],
                ref: selected,
                name: selected.split("/").at(-1) || selected,
              })
            }
          >
            Fix with agent
          </button>
        </article>
      )}
    </>
  );
}
