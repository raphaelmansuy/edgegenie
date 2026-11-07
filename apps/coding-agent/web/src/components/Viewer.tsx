/** Document viewer, now with a fenced editing surface (spec 003).
 *
 * The old header said "read-only on purpose", because a writable viewer would have been a second,
 * unfenced way to change the workspace. That comment could go because the fence moved: saving goes
 * through `scope.check_path` on the server — the same function the agent's tools call — so an editor
 * here is a *fenced* door rather than a hole.
 *
 * Three surfaces, chosen by what the document is:
 *
 *   notebook  -> EditorSurface with cells, when the reader did not truncate it
 *   file      -> EditorSurface as plain text, when likewise
 *   table     -> TableViewer (unchanged: a table is not a document you edit here)
 *
 * Read-only is not an apology. Saving a truncated document would silently drop the tail, so
 * refusing is the correct behaviour (spec 003 D7, ED-6).
 */
import { useCallback, useEffect, useState } from "react";
import { api, type TableInfo, type WsObject } from "../api/client";
import { ACTIONS, ACTIONS_FOR, type Action, type Doc } from "../domain/docs";
import { serializeCells, type Cell } from "../domain/notebook";
import { tokenize } from "../domain/highlight";
import { EditorSurface, type EditTarget } from "./EditorSurface";
import { ExtLink } from "./ExtLink";
import { Refresh } from "./Icons";
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
  /** Present when there is a session: the folder a save may enter without asking, and the session
   *  whose audit stream should receive the write. */
  editing?: {
    folder: string;
    sessionId: string | null;
    theme: "light" | "dark";
  };
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
        <button className="icon-btn" aria-label="Reload this document" title="Reload" onClick={reload} disabled={busy}>
          <Refresh size={15} className={busy ? "spin" : ""} />
        </button>
      </div>
      <button className="viewer-path" title="Copy the full path" aria-label={`Copy the path ${doc.ref}`}
        style={{ minHeight: 24, display: "inline-flex", alignItems: "center" }} onClick={() => {
        void navigator.clipboard?.writeText(doc.ref); setCopied(true); window.setTimeout(() => setCopied(false), 1200);
      }}>{copied ? "copied" : subtitle}</button>
      <div className="viewer-actions" role="toolbar" aria-label="Ask the agent about this">
        <button className="btn" onClick={() => actions.onAttach(doc)}>＠ Add to chat</button>
        <ExtLink className="btn" label={`Open ${doc.name} in Databricks`}
          target={{ kind: doc.kind, ref: doc.ref, objectId }}>Open in Databricks ↗</ExtLink>
        {ACTIONS_FOR[doc.kind].map((action) => (
          <button key={action} className="btn" onClick={() => actions.onAsk(action, doc)}>
            {ACTIONS[action].label}
          </button>
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

/** The version token, as the server computed it.
 *
 * This must NOT be re-derived on the client. An earlier version hashed the same three fields
 * locally with a different algorithm, so every first save was refused as a conflict: the client's
 * token could never equal the server's. The token is opaque by design — the server mints it, the
 * client carries it, nothing else interprets it.
 */
function versionOf(o: WsObject | null): string | null {
  return o?.version ?? null;
}

export function NotebookViewer({ doc, actions }: { doc: Doc; actions: ViewerActions }) {
  const { data, error, loading, reload } = useLoad<WsObject>(() => api.object(doc.ref), [doc.ref, doc.rev]);
  const isFile = data?.kind === "file";
  const [cells, setCells] = useState<Cell[] | null>(null);

  useEffect(() => {
    if (!data) return;
    if (isFile) { setCells(null); return; }
    // The server already parsed these cells. Adopting them directly is the whole point of one
    // shared Cell model — and re-serializing them here was a real corruption bug: server cells have
    // no client `id`, so `serializeCells` treated each `source` as a whole document and emitted
    // the header inside cell 1. Take the cells as given; only give them ids.
    setCells(data.cells.map((c, i) => ({
      id: `s${i}-${c.index}`,
      kind: c.kind as "code" | "markdown",
      language: c.language,
      source: c.source,
      ...(c.truncated ? { truncated: true } : {}),
    })));
  }, [data, isFile]);

  const onSaved = useCallback(() => { reload(); }, [reload]);

  const editable = Boolean(actions.editing && data && !data.truncated);
  // The editor's text is the cells serialized exactly once. This is the only place it happens, so
  // "what the user sees" and "what a save writes" cannot diverge.
  const source = data ? (isFile ? data.text : serializeCells(cells ?? [], (data.language || "PYTHON").toUpperCase())) : "";

  const target: EditTarget | null = data ? {
    path: doc.ref,
    name: doc.name,
    kind: isFile ? "file" : "notebook",
    language: (data.language || "PYTHON").toUpperCase(),
    version: versionOf(data),
    truncated: Boolean(data.truncated),
  } : null;

  /* When the editor is available, EditorSurface renders the one document bar. The old 128 px
     header must not also render, or the app pays for both — which is exactly what happened on the
     first attempt at this merge (measured: still 234 px of chrome after the bar was added). */
  const editingNow = Boolean(data && target && editable && actions.editing);

  return (
    <section className="viewer" aria-label={`${doc.name} viewer`}>
      {!editingNow && (
        <Head doc={doc} busy={loading} reload={reload} actions={actions} objectId={data?.objectId}
          subtitle={doc.ref} badge={data?.language ? data.language.toLowerCase() : undefined} />
      )}
      <div className="viewer-body">
        {loading && !data && <p className="viewer-note"><span className="spin" /> opening…</p>}
        {error && <p className="viewer-error" role="alert">{error}</p>}

        {editingNow && target && actions.editing && (
          <EditorSurface
            target={target}
            folder={actions.editing.folder}
            sessionId={actions.editing.sessionId}
            source={source}
            theme={actions.editing.theme}
            onSaved={onSaved}
            onCells={(next) => setCells(next)}
            onAskAction={(a) => actions.onAsk(a, doc)}
            onAttach={() => actions.onAttach(doc)}
            onOpenInDatabricks={() => { /* the ExtLink in Head did this; the bar uses the link */ }}
            onReload={reload}
          />
        )}

        {/* Read-only rendering: a table is not editable here, and a truncated document must not be
            saved, so the viewer shows it exactly as before. */}
        {data && !editable && !isFile && data.cells.length === 0 && <p className="viewer-note">This notebook has no cells.</p>}
        {data && !editable && !isFile && data.cells.map((c) => (
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
        {data && !editable && isFile && <Code text={data.text} language={data.language || "plain"} />}
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
