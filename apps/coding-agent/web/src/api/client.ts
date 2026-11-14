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

/** A project as the API actually describes it: no state, because a project has none. */
export interface LakebaseProject {
  ref: string; name: string; displayName: string;
  pgVersion?: number; owner?: string;
}
export interface LakebaseBranch { ref: string; name: string; isDefault: boolean; state: string; project?: string }
export type { LakebasePageData, AppView, AppHealth };

// -- jobs, runs and pipelines (spec 014) -------------------------------------------------------
// The shapes the adapter produces. Every field a page shows is here, and every block may arrive as
// `{error}` instead of data — the contract `Block` renders ([UI-3]).
export interface Schedule { cron: string; timezone: string; paused: boolean }

export interface JobTask {
  task_key: string;
  depends_on: string[];
  notebook_path?: string;
  python_file?: string;
  sql_file?: string;
  pipeline_id?: string;
  job_id?: string;
  timeout_seconds?: number;
  max_retries?: number;
}

export interface RunRow {
  run_id: number | null;
  job_id?: number | null;
  lifeCycle: string;
  result: string | null;
  word: string;
  tone: "good" | "busy" | "bad" | "quiet";
  startTime: number | null;
  endTime: number | null;
  duration: string;
  active: boolean;
  cancel: boolean;
  repair: boolean;
  message?: string;
  url?: string;
}

export interface TaskRun {
  taskKey: string;
  taskRunId: number | null;
  lifeCycle: string;
  result: string | null;
  word: string;
  tone: "good" | "busy" | "bad" | "quiet";
  duration: string;
  message?: string;
}

export interface RunOutput { taskKey?: string; error: string; traceTail?: string }

export interface JobRow {
  job_id: number | null;
  name: string;
  owner: string;
  schedule: Schedule | null;
  paused: boolean;
}

export interface JobFacts {
  job_id: number;
  name: string;
  owner: string;
  created: number | null;
  schedule: Schedule | null;
  tasks: JobTask[];
  queueing: boolean;
  timeoutSeconds: number;
  maxRetries: number;
  tags: Record<string, string>;
  performanceTarget: string;
}

export type MaybeError<T> = T | { error: string };

export interface JobPageData {
  job: MaybeError<JobFacts>;
  runs: MaybeError<RunRow[]>;
  latestRun: MaybeError<RunRow & { tasks?: TaskRun[]; output?: RunOutput; trigger?: string }> | null;
  levels: string[][];
  graphProblem: string | null;
  summary: string;
  identity: string;
}

export interface RunPageData extends RunRow {
  tasks: TaskRun[];
  output?: RunOutput;
  trigger?: string;
  /** The job's name, so a pasted run link carries context and not only an id ([RUN-1]). */
  jobName?: string;
}

export interface PipelineRow {
  pipeline_id: string;
  name: string;
  state: string;
  word: string;
  tone: "good" | "busy" | "bad" | "quiet";
  lastUpdate: { update_id: string; state: string; creationTime?: number } | null;
  catalog: string;
  creator: string;
}

export interface PipelineUpdate {
  updateId: string;
  state: string;
  word: string;
  tone: "good" | "busy" | "bad" | "quiet";
  creationTime: number | null;
  fullRefresh: boolean;
  cause: string;
  active: boolean;
}

export interface PipelineEvent {
  level: "ERROR" | "WARN" | "INFO" | string;
  message: string;
  timestamp: number | null;
  stackTrace: string;
}

export interface PipelineLibrary { kind: string; path: string }

export interface PipelineFacts {
  pipeline_id: string;
  name: string;
  state: string;
  catalog: string;
  schema: string;
  serverless: boolean;
  edition: string;
  channel: string;
  continuous: boolean;
  development: boolean;
  libraries: PipelineLibrary[];
  creator: string;
  storage: string;
}

export interface PipelinePageData {
  pipeline: MaybeError<PipelineFacts>;
  updates: MaybeError<PipelineUpdate[]>;
  lastUpdate: MaybeError<PipelineUpdate> | null;
  events: MaybeError<PipelineEvent[]>;
  word: string;
  tone: "good" | "busy" | "bad" | "quiet";
  activeUpdate: PipelineUpdate | null;
  identity: string;
}

export interface LedgerRow { kind: string; id: string; name: string; created: string; session: string }

export interface RunActionsView {
  word: string;
  tone: "good" | "busy" | "bad" | "quiet";
  active: boolean;
  terminal: boolean;
  cancel: boolean;
  repair: boolean;
}

export async function call<T>(path: string, init?: RequestInit): Promise<T> {
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
  /** What this conversation may change ([R-9]) and what it spent ([R-24]). */
  budget: (id: string) => call<import("../domain/budget").BudgetState>(`/api/sessions/${id}/budget`),
  compact: (id: string) =>
    call<Record<string, unknown>>(`/api/sessions/${id}/compact`, { method: "POST", headers: json }),
  config: () =>
    call<{ writeModes: { id: string; label: string; sentence: string; mutates: boolean }[];
           defaultWriteMode: string }>("/api/config"),
  sessions: () => call<{ sessions: SessionSummary[] }>("/api/sessions"),
  create: (folder: string, model?: string, schema?: string | null, writeMode?: string) =>
    call<SessionSummary>("/api/sessions", { method: "POST", headers: json,
      body: JSON.stringify({ folder, model, schema: schema ?? null, writeMode: writeMode ?? null }) }),
  session: (id: string) => call<SessionView & { turns: any[]; scope: any; running: number | null }>(`/api/sessions/${id}`),
  resume: (id: string) => call<SessionSummary>(`/api/sessions/${id}/resume`, { method: "POST" }),
  archive: (id: string) => call<void>(`/api/sessions/${id}`, { method: "DELETE" }),
  send: (id: string, text: string, key: string, attachments: Attachment[] = []) =>
    call<{ turnId: string; status?: import("../domain/events").TurnStatus }>(`/api/sessions/${id}/messages`, { method: "POST",
      headers: { ...json, "Idempotency-Key": key },
      // References only: the server reads the content with the user's own token, and a blob by its id.
      // `name` travels because it is the user's word for the file — the transcript renders it on reload,
      // and a chip that says "attachment" instead of "q3.csv" is a chip the user cannot recognise.
      body: JSON.stringify({ text, attachments: attachments.map(({ kind, ref, name }) => ({ kind, ref, name })) }) }),
  me: () => call<{ user: string; scratch: string; demo: boolean; workspace?: { host: string; orgId?: string };
    pythonRun?: import("../domain/cellrun").PythonPolicy }>("/api/me"),
  /** Which build the SERVER is. Distinct from `version(path)`, which is an object's revision token.
   *  `/api/health` answers the same for every build, so this is the only route that can tell a fresh
   *  deployment from a stale one. */
  build: () => call<{ version: string; commit: string; docs: string; source: string;
    releases: string; agentMode?: string }>("/api/version"),
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
  /**
   * Run a SQL cell on a warehouse, as the signed-in user. A statement can run for minutes, so this starts
   * it and polls (the Apps proxy cuts a long request), and resolves with the one result. `stop` is asked
   * between polls and cancels the statement on the warehouse.
   */
  runCell: async (
    language: string, source: string,
    hooks: { onStage?: (stage: string, seconds: number) => void; stop?: () => boolean; params?: Record<string, string> } = {},
  ): Promise<import("../domain/cellrun").CellRun> => {
    type Run = import("../domain/cellrun").CellRun;
    type Poll = { state: "running" | "done"; stage?: string; seconds: number; result?: Run };
    const started = await call<{ handle?: string; result?: Run }>(
      "/api/notebook/sql-runs", { method: "POST", headers: json, body: JSON.stringify({ language, source, params: hooks.params ?? {} }) });
    if (!started.handle) return started.result ?? { state: "failed", seconds: 0, error: "the app returned no result" };
    const url = `/api/notebook/sql-runs/${started.handle}`;
    const deadline = Date.now() + 12 * 60_000;
    let cancelled = false;
    for (;;) {
      await new Promise((r) => setTimeout(r, 800));
      if (!cancelled && hooks.stop?.()) { cancelled = true; await call(url, { method: "DELETE" }).catch(() => {}); }
      const poll = await call<Poll>(url);
      if (poll.state === "done" && poll.result) return poll.result;
      hooks.onStage?.(poll.stage ?? "running", poll.seconds);
      if (Date.now() > deadline) throw new Error("the query is taking longer than 12 minutes; it was left running on the warehouse");
    }
  },
  /**
   * Run one Python cell in the notebook's session (variables stay between cells). Starts it, then polls.
   * Resolves with the result, or `unavailable` (why a session cannot be used: the caller runs the cell
   * as a one-shot). `onProgress` sees what the cell has printed so far; `stop` is asked between polls and
   * interrupts the cell once.
   */
  runSessionCell: async (
    path: string, language: string, source: string, index: number,
    hooks: {
      /** Widget values to run with, by name. */
      widgets?: Record<string, string>;
      onProgress?: (p: { stage: string; seconds: number; outputs: import("../domain/cellrun").Output[] }) => void;
      onSession?: (s: import("../domain/session").SessionStatus) => void;
      stop?: () => boolean;
    } = {},
  ): Promise<{ result?: import("../domain/cellrun").CellRun; unavailable?: string; replaced?: string }> => {
    type Run = import("../domain/cellrun").CellRun;
    type Sess = import("../domain/session").SessionStatus;
    const started = await call<{ handle?: string; unavailable?: string; refused?: Run; replaced?: string; session?: Sess }>(
      "/api/notebook/kernels/run", { method: "POST", headers: json, body: JSON.stringify({ path, language, source, index, widgets: hooks.widgets ?? {} }) });
    if (started.unavailable) return { unavailable: started.unavailable };
    if (started.session) hooks.onSession?.(started.session);
    if (!started.handle) {
      return { result: started.refused ?? { state: "failed", seconds: 0, error: "the app returned no result" } };
    }
    const url = `/api/notebook/kernels/runs/${started.handle}`;
    const deadline = Date.now() + 5 * 3600_000;
    let interrupted = false;
    for (;;) {
      await new Promise((r) => setTimeout(r, 800));
      if (!interrupted && hooks.stop?.()) { interrupted = true; await call(url, { method: "DELETE" }).catch(() => {}); }
      const poll = await call<{ state: "running" | "done"; stage?: string; seconds: number; outputs?: import("../domain/cellrun").Output[];
        result?: Run; session?: Sess }>(url);
      if (poll.session) hooks.onSession?.(poll.session);
      if (poll.state === "done" && poll.result) return { result: poll.result, replaced: started.replaced };
      hooks.onProgress?.({ stage: poll.stage ?? "running", seconds: poll.seconds, outputs: poll.outputs ?? [] });
      if (Date.now() > deadline) throw new Error("the cell has been running for more than 5 hours; it was left running in its session");
    }
  },
  sessionStatus: (path: string) =>
    call<import("../domain/session").SessionStatus>(`/api/notebook/kernels?path=${encodeURIComponent(path)}`),
  stopSession: (path: string) =>
    call<import("../domain/session").SessionStatus>(`/api/notebook/kernels?path=${encodeURIComponent(path)}`, { method: "DELETE" }),
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

  // -- jobs, runs and pipelines (spec 014) -----------------------------------------------------
  // There is NO write call here, and that is a decision rather than an omission: every action (run,
  // resume, cancel, repair, start, stop) goes through the agent, so the write fence has one home
  // ([07 §5]). `test_infra_routes.py` asserts the route table has no POST for these prefixes.
  jobs: (limit = 25) => call<{ items: JobRow[]; identity: string }>(`/api/jobs?limit=${limit}`),
  job: (id: string | number) => call<JobPageData>(`/api/jobs/${encodeURIComponent(String(id))}`),
  run: (id: string | number) => call<RunPageData>(`/api/runs/${encodeURIComponent(String(id))}`),
  pipelines: (limit = 25) =>
    call<{ items: PipelineRow[]; identity: string }>(`/api/pipelines?limit=${limit}`),
  pipeline: (id: string, events = 20) =>
    call<PipelinePageData>(`/api/pipelines/${encodeURIComponent(id)}?events=${events}`),
  pipelineEvents: (id: string, limit = 20) =>
    call<{ items: PipelineEvent[] }>(`/api/pipelines/${encodeURIComponent(id)}/events?limit=${limit}`),
  /** What this conversation created, so a page only offers the controls it may use ([TOOL-6]). */
  ledger: () => call<{ items: LedgerRow[] }>("/api/infra/ledger"),
  /** Which controls belong on screen for a run's state, answered by the domain module. */
  runActions: (lifeCycle: string, result = "") =>
    call<RunActionsView>(`/api/infra/run-actions?life_cycle=${encodeURIComponent(lifeCycle)}&result=${encodeURIComponent(result)}`),
};
