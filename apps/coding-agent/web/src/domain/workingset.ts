/** Reload recovery: bounded document metadata, isolated by account/workspace and browser tab.
 * Never stores content, tokens, model settings or grants. The URL remains authoritative for selection.
 */
import { makeDoc, type Doc } from "./docs";
export interface WorkingSet { docs: Doc[]; active: string; closed: { doc: Doc; index: number }[] }
const key = (scope: string) => `coding-agent:working-set:v1:${encodeURIComponent(scope)}`;
const MAX = 100;
function documentOf(value: unknown): Doc | null {
  const d = value as Partial<Doc> | null;
  if (!d || !["file", "notebook", "table", "lakebase", "app", "job", "pipeline", "run", "query", "query-draft"].includes(d.kind ?? "") || typeof d.ref !== "string" || !d.ref || d.ref.length > 2048) return null;
  if (["file","notebook"].includes(d.kind!) && !d.ref.startsWith("/")) return null;
  return makeDoc(d.kind!, d.ref);
}
export function parseWorkingSet(raw: string | null): WorkingSet {
  const empty = { docs: [], active: "chat", closed: [] };
  try {
    const data = JSON.parse(raw ?? "null");
    if (!data || data.version !== 1 || !Array.isArray(data.docs)) return empty;
    const ids = new Set<string>();
    const docs = data.docs.slice(0, MAX).map(documentOf).filter((d: Doc | null): d is Doc => !!d && !ids.has(d.id) && !!ids.add(d.id));
    const closed = (Array.isArray(data.closed) ? data.closed.slice(-20) : []).flatMap((entry: { doc?: unknown; index?: number }) => {
      const doc = documentOf(entry?.doc);
      return doc && Number.isInteger(entry.index) && entry.index! >= 0 ? [{ doc, index: Math.min(entry.index!, MAX) }] : [];
    });
    return { docs, active: data.active === "chat" || docs.some((d: Doc) => d.id === data.active) ? data.active : docs[0]?.id ?? "chat", closed };
  } catch { return empty; }
}
export function readWorkingSet(scope: string): WorkingSet {
  try { return parseWorkingSet(sessionStorage.getItem(key(scope))); } catch { return parseWorkingSet(null); }
}
export function saveWorkingSet(scope: string, docs: Doc[], active: string, closed: WorkingSet["closed"]): void {
  const metadata = (doc: Doc) => ({ kind: doc.kind, ref: doc.ref });
  try { sessionStorage.setItem(key(scope), JSON.stringify({ version: 1, docs: docs.slice(0, MAX).map(metadata), active,
    closed: closed.slice(-20).map((entry) => ({ doc: metadata(entry.doc), index: entry.index })) })); } catch { /* blocked/full storage never prevents editing */ }
}
