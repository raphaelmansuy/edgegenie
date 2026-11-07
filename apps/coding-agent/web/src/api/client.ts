/** Typed API client. One place that knows the HTTP surface. */
import type { Attachment, SessionView } from "../domain/events";

const json = { "Content-Type": "application/json" };

export interface SessionSummary {
  id: string; title: string; folder: string; model: string; status: string; tools: number;
  /** Epoch seconds. Absent for a session created before this field existed. */
  createdAt?: number;
}

export interface Cell { index: number; kind: "code" | "markdown"; language: string; source: string; truncated: boolean }
export interface WsObject {
  objectId?: string;
  path: string; name: string; kind: "notebook" | "file"; language: string; size: number;
  truncated: boolean; cells: Cell[]; text: string;
}
export interface WsHit { path: string; name: string; kind: string; language?: string }
export interface CatalogItem { kind: "catalog" | "schema" | "table"; name: string; ref: string; tableType?: string; comment?: string }
export interface TableInfo {
  fullName: string; tableType: string; owner: string; comment: string; format: string;
  columns: { name: string; type: string; nullable: boolean; comment: string }[];
}

export interface ModelOption { id: string; name: string; default?: boolean }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch { /* non-JSON error body */ }
    throw new ApiError(r.status, detail);
  }
  return (r.status === 204 ? (undefined as T) : ((await r.json()) as T));
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const api = {
  models: () => call<{ available: ModelOption[]; default: string }>("/api/models"),
  sessions: () => call<{ sessions: SessionSummary[] }>("/api/sessions"),
  create: (folder: string, model?: string, schema?: string | null) =>
    call<SessionSummary>("/api/sessions", { method: "POST", headers: json,
      body: JSON.stringify({ folder, model, schema: schema ?? null }) }),
  session: (id: string) => call<SessionView & { turns: any[]; scope: any; running: number | null }>(`/api/sessions/${id}`),
  archive: (id: string) => call<void>(`/api/sessions/${id}`, { method: "DELETE" }),
  send: (id: string, text: string, key: string, attachments: Attachment[] = []) =>
    call<{ turnId: string }>(`/api/sessions/${id}/messages`, { method: "POST",
      headers: { ...json, "Idempotency-Key": key },
      // references only: the server reads the content with the user's own token
      body: JSON.stringify({ text, attachments: attachments.map(({ kind, ref }) => ({ kind, ref })) }) }),
  me: () => call<{ user: string; scratch: string; demo: boolean; workspace?: { host: string; orgId?: string } }>("/api/me"),
  object: (path: string) => call<WsObject>(`/api/workspace/object?path=${encodeURIComponent(path)}`),
  search: (q: string, path?: string, signal?: AbortSignal) =>
    call<{ root: string; complete: boolean; results: WsHit[] }>(
      `/api/workspace/search?q=${encodeURIComponent(q)}${path ? `&path=${encodeURIComponent(path)}` : ""}`,
      { signal }),
  mkdir: (path: string) => call<{ path: string }>("/api/workspace/mkdir", { method: "POST", headers: json,
    body: JSON.stringify({ path }) }),
  findTables: (q: string) => call<{ results: CatalogItem[] }>(`/api/catalog/find?q=${encodeURIComponent(q)}`),
  catalog: (catalog = "", schema = "") =>
    call<{ items: CatalogItem[] }>(`/api/catalog?catalog=${encodeURIComponent(catalog)}&schema=${encodeURIComponent(schema)}`),
  table: (name: string) => call<TableInfo>(`/api/catalog/table?name=${encodeURIComponent(name)}`),
  preview: (name: string) => call<{ columns: string[]; rows: (string | null)[][]; warehouse: string }>(
    `/api/catalog/preview?name=${encodeURIComponent(name)}`),
  cancel: (id: string) => call<{ cancelled: boolean }>(`/api/sessions/${id}/cancel`, { method: "POST" }),
  decide: (sid: string, approvalId: string, outcome: string, optionId?: string) =>
    call<{ ok: boolean }>(`/api/approvals/${sid}/${approvalId}`, { method: "POST", headers: json,
      body: JSON.stringify({ outcome, optionId }) }),
  setModel: (id: string, model: string) =>
    call<{ current: string; available: string[] }>(`/api/sessions/${id}/model`, { method: "POST",
      headers: json, body: JSON.stringify({ model }) }),
};
