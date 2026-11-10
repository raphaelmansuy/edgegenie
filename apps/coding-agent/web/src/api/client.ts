/** Typed API client. One place that knows the HTTP surface. */
import type { Attachment, SessionView } from "../domain/events";
import type { CatalogueResponse, ModelSpec } from "../domain/models";
import type { ModelConfig } from "../domain/modelconfig";

const json = { "Content-Type": "application/json" };

export interface SessionSummary {
  id: string; title: string; folder: string; model: string; status: string; tools: number;
  /** Epoch seconds. Absent for a session created before this field existed. */
  createdAt?: number;
  requiresResume?: boolean;
  execution?: import("../domain/mission").Execution;
}

export interface Cell { index: number; kind: "code" | "markdown"; language: string; source: string; truncated: boolean }
export interface WsObject {
  objectId?: string;
  /** Epoch seconds from the workspace API. With objectId and size it forms the version token a
   *  save compares (spec 003 CX-1). */
  modifiedAt?: number;
  /** The server's version token. Opaque; send it back on save. */
  version?: string;
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

export type { CatalogueResponse, ModelSpec };

export interface CredentialView {
  id: string;
  provider: string;
  kind: string;
  scope: string;
  last4: string;
  projectHint: string;
  fingerprint: string;
}

export interface LlmHealth {
  source: string;
  updatedAt: string;
  vault: { mode: string; available: boolean };
  providers: {
    id: string; name: string; models: number; usable: number;
    state: string; detail: string; lastProbe: string | null;
  }[];
}

export interface SaveCredentialResult {
  credential: CredentialView;
  saved: boolean;
}

import { errorText } from "../domain/apierror";
import type { AppHealth, AppView } from "../domain/app";
import type { LakebasePageData } from "../domain/lakebase";

/** A Lakebase project's ref contains slashes; each segment is encoded and the slashes are kept, which
 *  is how the server's `{ref:path}` route reads it. */
const encodePath = (ref: string) =>
  ref.split("/").filter(Boolean).map(encodeURIComponent).join("/");

export interface LakebaseProject {
  ref: string; name: string; displayName: string; state: string; stateRaw: string; ready: boolean;
}
export interface LakebaseBranch { ref: string; name: string; isDefault: boolean; state: string; project?: string }
export type { LakebasePageData, AppView, AppHealth };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = errorText(await r.json(), detail);
    } catch { /* non-JSON error body */ }
    throw new ApiError(r.status, detail);
  }
  return (r.status === 204 ? (undefined as T) : ((await r.json()) as T));
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export interface ModelFacts {
  current: string;
  resolved: {
    id: string; provider: string; wire: string; endpoint: string;
    context: number; output: number; evidence: string; source: string;
    capability: string; credentialRef: string;
  } | null;
  turns: { index: number; turnId: string; model: string; provider: string; wire: string; endpoint: string }[];
  /** The 1-based turn index at which the model changed, or null when it never did. */
  switchAtTurn: number | null;
}

export const api = {
  /** Model configuration for the settings screen (what is switched on, who may change it, where it is saved). */
  llmConfig: () => call<ModelConfig>("/api/llm/config"),
  addModel: (body: { provider: string; model: string; name: string; context: number; output: number;
                     capability?: string; makeDefault?: boolean }) =>
    call<{ saved: boolean }>("/api/llm/config/models", { method: "POST", headers: json, body: JSON.stringify(body) }),
  setModelEnabled: (id: string, enabled: boolean) =>
    call<{ saved: boolean }>(`/api/llm/config/models/${id}`, { method: "PATCH", headers: json, body: JSON.stringify({ enabled }) }),
  removeModel: (id: string) => call<void>(`/api/llm/config/models/${id}`, { method: "DELETE" }),
  setDefaultModel: (model: string) =>
    call<{ saved: boolean; default: string }>("/api/llm/config/default", { method: "PUT", headers: json, body: JSON.stringify({ model }) }),
  patchProvider: (id: string, body: { enabled?: boolean; baseUrl?: string }) =>
    call<{ saved: boolean }>(`/api/llm/config/providers/${id}`, { method: "PATCH", headers: json, body: JSON.stringify(body) }),
  models: () => call<CatalogueResponse>("/api/models"),
  /** Upload bytes the user handed the browser (paste, drop, picker). The only route that takes content. */
  uploadBlob: (sessionId: string | null, name: string, mime: string, contentB64: string) =>
    call<{ blobId: string; name: string; mime: string; bytes: number; family: string; state: string }>(
      "/api/blobs", { method: "POST", headers: json,
        body: JSON.stringify({ sessionId, name, mime, content: contentB64 }) }),
  /** Where a chip's thumbnail comes from. A URL, not a fetch: the browser caches it per blob. */
  blobUrl: (blobId: string, thumb = false) => `/api/blobs/${blobId}${thumb ? "?thumb=1" : ""}`,
  /** Write a blob into the workspace, fenced. `sessionId` lets the fence judge against the session scope. */
  materialiseBlob: (blobId: string, folder: string, sessionId: string, approval?: string) =>
    call<{ path: string; bytes: number }>(`/api/blobs/${blobId}/materialise`, {
      method: "POST", headers: json, body: JSON.stringify({ folder, sessionId, approval }) }),
  /** The full catalogue: state, limits with evidence, capability and credential hint per model. */
  catalogue: () => call<CatalogueResponse>("/api/llm/models"),
  model: (id: string) => call<ModelSpec>(`/api/llm/models/${id}`),
  llmHealth: () => call<LlmHealth>("/api/llm/health"),
  credentials: () => call<{ credentials: CredentialView[]; vault: { mode: string; available: boolean }; canSave: boolean }>("/api/llm/credentials"),
  saveCredential: (provider: string, kind: string, secret: string, scope = "user") =>
    call<SaveCredentialResult>("/api/llm/credentials", {
      method: "PUT", headers: json, body: JSON.stringify({ provider, kind, secret, scope }) }),
  testCredential: (provider: string, kind: string, secret: string, model?: string) =>
    call<{ ok: boolean; state?: string; detail?: string; field?: string; copy?: string;
           credential?: CredentialView }>("/api/llm/credentials/test", {
      method: "POST", headers: json, body: JSON.stringify({ provider, kind, secret, model }) }),
  revokeCredential: (ref: string) =>
    call<void>(`/api/llm/credentials/${encodeURIComponent(ref)}`, { method: "DELETE" }),
  probeModel: (model: string) => call<{ model: string; state: string; detail: string }>(
    "/api/llm/models/probe", { method: "POST", headers: json, body: JSON.stringify({ model }) }),
  refreshDiscovery: () => call<CatalogueResponse>("/api/llm/discovery/refresh", { method: "POST" }),
  modelFacts: (id: string) => call<ModelFacts>(`/api/sessions/${id}/model-facts`),
  sessions: () => call<{ sessions: SessionSummary[] }>("/api/sessions"),
  create: (folder: string, model?: string, schema?: string | null) =>
    call<SessionSummary>("/api/sessions", { method: "POST", headers: json,
      body: JSON.stringify({ folder, model, schema: schema ?? null }) }),
  session: (id: string) => call<SessionView & { turns: any[]; scope: any; running: number | null }>(`/api/sessions/${id}`),
  resume: (id: string) => call<SessionSummary>(`/api/sessions/${id}/resume`, { method: "POST" }),
  archive: (id: string) => call<void>(`/api/sessions/${id}`, { method: "DELETE" }),
  send: (id: string, text: string, key: string, attachments: Attachment[] = []) =>
    call<{ turnId: string }>(`/api/sessions/${id}/messages`, { method: "POST",
      headers: { ...json, "Idempotency-Key": key },
      // References only: the server reads the content with the user's own token, and a blob by its id.
      // `name` travels because it is the user's word for the file — the transcript renders it on reload,
      // and a chip that says "attachment" instead of "q3.csv" is a chip the user cannot recognise.
      body: JSON.stringify({ text, attachments: attachments.map(({ kind, ref, name }) => ({ kind, ref, name })) }) }),
  me: () => call<{ user: string; scratch: string; demo: boolean; workspace?: { host: string; orgId?: string };
    pythonRun?: import("../domain/cellrun").PythonPolicy }>("/api/me"),
  object: (path: string) => call<WsObject>(`/api/workspace/object?path=${encodeURIComponent(path)}`),
  /** The version token only: one `get-status`, no content. Comparable with `WsObject.version`. */
  version: (path: string) => call<{ path: string; version: string; modifiedAt: number }>(`/api/workspace/version?path=${encodeURIComponent(path)}`),
  search: (q: string, path?: string, signal?: AbortSignal) =>
    call<{ root: string; complete: boolean; results: WsHit[] }>(
      `/api/workspace/search?q=${encodeURIComponent(q)}${path ? `&path=${encodeURIComponent(path)}` : ""}`,
      { signal }),
  mkdir: (path: string) => call<{ path: string }>("/api/workspace/mkdir", { method: "POST", headers: json,
    body: JSON.stringify({ path }) }),
  createObject: (parent: string, name: string, kind: "notebook" | "file" | "folder", language?: string) =>
    call<{ path: string }>("/api/workspace/object", { method: "POST", headers: json,
      body: JSON.stringify({ parent, name, kind, language }) }),
  importObject: (parent: string, name: string, content: string, format: string, language?: string) =>
    call<{ path: string }>("/api/workspace/import", { method: "POST", headers: json,
      body: JSON.stringify({ parent, name, content, format, language }) }),
  removeObject: (path: string, recursive: boolean) =>
    call<{ path: string }>("/api/workspace/delete", { method: "POST", headers: json,
      body: JSON.stringify({ path, recursive }) }),
  transferObject: (source: string, destination: string, mode: "copy" | "move") =>
    call<{ path: string }>("/api/workspace/transfer", { method: "POST", headers: json,
      body: JSON.stringify({ source, destination, mode }) }),
  permissions: (path: string) => call<{ path: string; entries: { who: string; principal: string; permission: string; inherited: boolean }[] }>(
    `/api/workspace/permissions?path=${encodeURIComponent(path)}`),
  /** Execute one cell (SQL only). Returns a run state plus either data or a reason. */
  runCell: (language: string, source: string) =>
    call<import("../domain/cellrun").CellRun>("/api/notebook/run-cell", { method: "POST", headers: json,
      body: JSON.stringify({ language, source }) }),
  /**
   * Run Python cells on serverless compute AS THE APP (administrators only; the server decides).
   * `show` are the cells (0-based) whose output is wanted; the Python cells above the last of them run
   * first, for their variables. A run takes a minute or more on cold compute, so this starts it and then
   * polls, and resolves with one result per cell asked for. `stop` is asked between polls.
   */
  runPython: async (
    cells: { language: string; source: string }[], show: number[],
    hooks: { onStage?: (stage: string, seconds: number) => void; stop?: () => boolean } = {},
  ): Promise<Record<string, import("../domain/cellrun").CellRun>> => {
    type Poll = { state: "running" | "done"; stage?: string; seconds: number;
      results?: Record<string, import("../domain/cellrun").CellRun> };
    const started = await call<{ handle?: string; refused?: Record<string, import("../domain/cellrun").CellRun> }>(
      "/api/notebook/python-runs", { method: "POST", headers: json, body: JSON.stringify({ cells, show }) });
    if (!started.handle) return started.refused ?? {};
    const url = `/api/notebook/python-runs/${started.handle}`;
    const deadline = Date.now() + 20 * 60_000;
    let cancelled = false;
    for (;;) {
      await new Promise((r) => setTimeout(r, 1500));
      if (!cancelled && hooks.stop?.()) { cancelled = true; await call(url, { method: "DELETE" }).catch(() => {}); }
      const poll = await call<Poll>(url);
      if (poll.state === "done") return { ...(started.refused ?? {}), ...(poll.results ?? {}) };
      hooks.onStage?.(poll.stage ?? "working", poll.seconds);
      if (Date.now() > deadline) throw new Error("the run is taking longer than 20 minutes; it was left running in Databricks");
    }
  },
  download: async (path: string, format: string, filename: string) => {
    const r = await fetch(`/api/workspace/export?path=${encodeURIComponent(path)}&format=${encodeURIComponent(format)}`);
    if (!r.ok) {
      let detail = r.statusText;
      try { detail = (await r.json()).detail ?? detail; } catch { /* bytes, not JSON */ }
      throw new ApiError(r.status, detail);
    }
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  },
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
    call<{ current: string; available: string[]; restartRequired?: boolean }>(
      `/api/sessions/${id}/model`, { method: "POST", headers: json, body: JSON.stringify({ model }) }),

  // -- Lakebase and Databricks Apps (spec 013) ------------------------------------------------
  // One call per object: a project page asks for the whole page and receives four independent
  // blocks, any of which may be `{error}` instead of data ([UI-3], [E-11]).
  lakebaseProjects: () => call<{ items: LakebaseProject[] }>("/api/lakebase/projects"),
  lakebaseProject: (ref: string, branch = "production") =>
    call<LakebasePageData>(`/api/lakebase/projects/${encodePath(ref)}?branch=${encodeURIComponent(branch)}`),
  lakebaseBranches: (ref: string) =>
    call<{ items: LakebaseBranch[] }>(`/api/lakebase/projects/${encodePath(ref)}/branches`),
  lakebaseTables: (ref: string, branch: string, database: string, schema: string) =>
    call<{ schema: string; tables: string[]; truncated: boolean }>(
      `/api/lakebase/projects/${encodePath(ref)}/tables?branch=${encodeURIComponent(branch)}`
      + `&database=${encodeURIComponent(database)}&schema=${encodeURIComponent(schema)}`),
  refreshLakebase: (ref: string) =>
    call<{ refreshed: boolean }>(`/api/lakebase/projects/${encodePath(ref)}/refresh`, { method: "POST" }),
  apps: (lakebase = "") => call<{ items: AppView[] }>(`/api/apps${lakebase ? `?lakebase=${encodeURIComponent(lakebase)}` : ""}`),
  app: (name: string, health = true) => call<AppView>(`/api/apps/${encodeURIComponent(name)}?health=${health}`),
  appHealth: (name: string, fresh = false) =>
    call<AppHealth>(`/api/apps/${encodeURIComponent(name)}/health?fresh=${fresh}`),
};
