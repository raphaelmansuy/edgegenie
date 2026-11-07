/** Document viewer: a notebook as cells, a file as text, a table as schema plus sample rows.
 *
 * Read-only on purpose. Editing happens through the agent (which is fenced and audited), so a
 * viewer that could also write would be a second, unfenced way to change the workspace.
 */
import { useCallback, useEffect, useState } from "react";
import { api, type TableInfo, type WsObject } from "../api/client";
import { ACTIONS, ACTIONS_FOR, type Action, type Doc } from "../domain/docs";
import { tokenize } from "../domain/highlight";
import { ExtLink } from "./ExtLink";
import { Markdown } from "./Markdown";

export function Code({ text, language }: { text: string; language: string }) {
  return (
    <pre className="code" data-language={language}>
      <code>{tokenize(text, language).map((t, i) => (t.cls === "plain" ? t.text : <span key={i} className={`tk-${t.cls}`}>{t.text}</span>))}</code>
    </pre>
  );
}

function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, set] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const run = useCallback(() => {
    let live = true;
    set((s) => ({ data: s.data, loading: true }));
    load().then((data) => live && set({ data, loading: false }))
      .catch((e) => live && set({ error: e instanceof Error ? e.message : "could not load", loading: false }));
    return () => { live = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => run(), [run]);
  return { ...state, reload: run };
}

export interface ViewerActions {
  onAsk: (a: Action, doc: Doc) => void;
  onAttach: (doc: Doc) => void;
}

function Head({ doc, subtitle, badge, actions, busy, reload, objectId }: {
  doc: Doc; subtitle: string; badge?: string; actions: ViewerActions; busy: boolean; reload: () => void; objectId?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <header className="viewer-head">
      <div className="viewer-title">
        <span className="viewer-name">{doc.name}</span>
        {badge && <span className="tree-lang big">{badge}</span>}
        <button className="btn ghost sm" aria-label="Reload" title="Reload" onClick={reload} disabled={busy}>⟳</button>
      </div>
      <button className="viewer-path" title="Copy the full path" aria-label={`Copy the path ${doc.ref}`}
        style={{ minHeight: 24, display: "inline-flex", alignItems: "center" }} onClick={() => {
        void navigator.clipboard?.writeText(doc.ref); setCopied(true); window.setTimeout(() => setCopied(false), 1200);
      }}>{copied ? "copied" : subtitle}</button>
      <div className="viewer-actions" role="toolbar" aria-label="Ask the agent about this">
        <button className="btn" onClick={() => actions.onAttach(doc)}>＠ Add to chat</button>
        <ExtLink className="btn" label={`Open ${doc.name} in Databricks`}
          target={{ kind: doc.kind, ref: doc.ref, objectId }}>Open in Databricks ↗</ExtLink>
        {ACTIONS_FOR[doc.kind].map((a) => (
          <button key={a} className="btn" onClick={() => actions.onAsk(a, doc)}>{ACTIONS[a].label}</button>
        ))}
      </div>
    </header>
  );
}

/** Copy one cell. Reading a notebook is often the start of reusing a line from it. */
function CellCopy({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button className="cell-copy" aria-label="Copy this cell" title="Copy this cell"
      onClick={() => {
        void navigator.clipboard?.writeText(text);
        setDone(true);
        window.setTimeout(() => setDone(false), 1200);
      }}>{done ? "copied" : "copy"}</button>
  );
}

export function NotebookViewer({ doc, actions }: { doc: Doc; actions: ViewerActions }) {
  const { data, error, loading, reload } = useLoad<WsObject>(() => api.object(doc.ref), [doc.ref, doc.rev]);
  const isFile = data?.kind === "file";
  return (
    <section className="viewer" aria-label={`${doc.name} viewer`}>
      <Head doc={doc} busy={loading} reload={reload} actions={actions} objectId={data?.objectId}
        subtitle={doc.ref} badge={data?.language ? data.language.toLowerCase() : undefined} />
      <div className="viewer-body">
        {loading && !data && <p className="viewer-note"><span className="spin" /> opening…</p>}
        {error && <p className="viewer-error" role="alert">{error}</p>}
        {data && !isFile && data.cells.length === 0 && <p className="viewer-note">This notebook has no cells.</p>}
        {data && !isFile && data.cells.map((c) => (
          <div key={c.index} className={`cell cell-${c.kind}`}>
            <div className="cell-gutter" aria-hidden>
              <span>{c.index + 1}</span>
              {c.kind === "code" && <span className="cell-lang">{c.language.slice(0, 3)}</span>}
            </div>
            <div className="cell-main">
              <CellCopy text={c.source} />
              {c.kind === "markdown" ? <Markdown text={c.source} /> : <Code text={c.source} language={c.language} />}
              {c.truncated && <p className="viewer-note">This cell is longer than the viewer shows. The agent can read all of it.</p>}
            </div>
          </div>
        ))}
        {data && isFile && <Code text={data.text} language={data.language || "plain"} />}
        {data?.truncated && <p className="viewer-note">Showing the first 400 KB. The agent reads the rest in pages.</p>}
      </div>
    </section>
  );
}

export function TableViewer({ doc, actions }: { doc: Doc; actions: ViewerActions }) {
  const { data, error, loading, reload } = useLoad<TableInfo>(() => api.table(doc.ref), [doc.ref, doc.rev]);
  const [sample, setSample] = useState<{ columns: string[]; rows: (string | null)[][]; warehouse: string } | null>(null);
  const [sampling, setSampling] = useState(false);
  const [sampleErr, setSampleErr] = useState("");

  useEffect(() => { setSample(null); setSampleErr(""); }, [doc.ref]);

  const run = async () => {
    setSampling(true); setSampleErr("");
    try { setSample(await api.preview(doc.ref)); }
    catch (e) { setSampleErr(e instanceof Error ? e.message : "preview failed"); }
    finally { setSampling(false); }
  };

  return (
    <section className="viewer" aria-label={`${doc.name} table`}>
      <Head doc={doc} busy={loading} reload={reload} actions={actions}
        subtitle={doc.ref} badge={data ? data.tableType.toLowerCase().replace("_", " ") || "table" : undefined} />
      <div className="viewer-body">
        {loading && !data && <p className="viewer-note"><span className="spin" /> reading the schema…</p>}
        {error && <p className="viewer-error" role="alert">{error}</p>}
        {data && (
          <>
            {data.comment && <p className="viewer-comment">{data.comment}</p>}
            <dl className="kv table-kv">
              <dt>owner</dt><dd>{data.owner || "—"}</dd>
              <dt>format</dt><dd>{data.format || "—"}</dd>
              <dt>columns</dt><dd>{data.columns.length}</dd>
            </dl>
            <h3 className="viewer-h">Columns</h3>
            <table className="grid">
              <thead><tr><th>#</th><th>name</th><th>type</th><th>comment</th></tr></thead>
              <tbody>
                {data.columns.map((c, i) => (
                  <tr key={c.name}><td className="num">{i + 1}</td><td><code>{c.name}</code></td>
                    <td className="type">{c.type}</td><td>{c.comment}</td></tr>
                ))}
              </tbody>
            </table>
            <h3 className="viewer-h">Sample rows</h3>
            {!sample && (
              <button className="btn" onClick={() => void run()} disabled={sampling}>
                {sampling ? "Running on a warehouse…" : "Show 10 rows"}
              </button>
            )}
            {sampleErr && <p className="viewer-error" role="alert">{sampleErr}</p>}
            {sample && (
              <>
                <div className="grid-wrap">
                  <table className="grid">
                    <thead><tr>{sample.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                    <tbody>{sample.rows.map((r, i) => (
                      <tr key={i}>{r.map((v, j) => <td key={j}>{v === null ? <em>null</em> : v}</td>)}</tr>
                    ))}</tbody>
                  </table>
                </div>
                <p className="viewer-note">Read with your permissions on {sample.warehouse || "a SQL warehouse"}.</p>
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}
