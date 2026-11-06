/** Typed API client. One place that knows the HTTP surface. */
import type { SessionView } from "../domain/events";

const json = { "Content-Type": "application/json" };

export interface SessionSummary {
  id: string; title: string; folder: string; model: string; status: string; tools: number;
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
  send: (id: string, text: string, key: string) =>
    call<{ turnId: string }>(`/api/sessions/${id}/messages`, { method: "POST",
      headers: { ...json, "Idempotency-Key": key }, body: JSON.stringify({ text }) }),
  cancel: (id: string) => call<{ cancelled: boolean }>(`/api/sessions/${id}/cancel`, { method: "POST" }),
  decide: (sid: string, approvalId: string, outcome: string, optionId?: string) =>
    call<{ ok: boolean }>(`/api/approvals/${sid}/${approvalId}`, { method: "POST", headers: json,
      body: JSON.stringify({ outcome, optionId }) }),
  setModel: (id: string, model: string) =>
    call<{ current: string; available: string[] }>(`/api/sessions/${id}/model`, { method: "POST",
      headers: json, body: JSON.stringify({ model }) }),
};
