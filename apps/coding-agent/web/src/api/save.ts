/** The save client: one place that talks to `/api/workspace/fence` and `/api/workspace/save`.
 *
 * Everything about failure is decided here, so the components never branch on an HTTP status:
 *
 *  - `ok`        the object landed; carries the new version token
 *  - `ask`       the fence wants approval; carries a token bound to this path and version
 *  - `conflict`  somebody else wrote; carries both versions so the UI can offer a choice (CX-3)
 *  - `error`     anything else, with a sentence fit to show a person
 *
 * This mirrors how the transcript handles stream events: the component renders a state, not a
 * status code.
 */

export interface SavedOk {
  kind: "ok";
  path: string;
  size: number;
  version: string | null;
}

export interface SavedAsk {
  kind: "ask";
  path: string;
  reason: string;
  /** Approval token to send back with the retry. */
  approval: string;
}

export interface SavedConflict {
  kind: "conflict";
  path: string;
  /** The version the server holds now, if it could tell. */
  current: string | null;
  /** The version the client sent. */
  yours: string | null;
  reason: string;
}

export interface SavedError {
  kind: "error";
  path: string;
  message: string;
  /** True when retrying the same request could plausibly work (a network blip, a 5xx). */
  retryable: boolean;
}

export type SaveResult = SavedOk | SavedAsk | SavedConflict | SavedError;

export interface FenceAnswer {
  verdict: "allow" | "ask" | "deny";
  reason: string;
  approval: string | null;
}

async function post<T>(url: string, body: unknown): Promise<{ status: number; body: T | null }> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let parsed: T | null = null;
  try { parsed = (await r.json()) as T; } catch { /* an empty or non-JSON body is not fatal */ }
  return { status: r.status, body: parsed };
}

/** What would the fence say about this path? Asked before the user types (WR-5). */
export async function askFence(path: string, sessionId: string | null, version: string | null): Promise<FenceAnswer> {
  const { status, body } = await post<FenceAnswer>("/api/workspace/fence", { path, sessionId, version });
  if (status === 200 && body) return body;
  // Failing open would be a lie about the fence; failing closed means "ask", which is safe.
  return { verdict: "ask", reason: "could not check the fence", approval: null };
}

export interface SaveRequest {
  path: string;
  text: string;
  /** The token the buffer was loaded from. `null` means "this is a create". */
  version: string | null;
  sessionId: string | null;
  approval?: string | null;
  language?: string | null;
}

export async function saveDocument(req: SaveRequest): Promise<SaveResult> {
  const payload = {
    path: req.path,
    text: req.text,
    // `""` is how the protocol says "there is no prior version, this is a create". `null` would be
    // indistinguishable from "the client forgot", which the server refuses on an existing object.
    version: req.version ?? "",
    sessionId: req.sessionId,
    approval: req.approval ?? null,
    language: req.language ?? null,
  };

  let response: { status: number; body: unknown };
  try {
    response = await post<unknown>("/api/workspace/save", payload);
  } catch (e) {
    return {
      kind: "error", path: req.path, retryable: true,
      message: e instanceof Error ? `could not reach the server: ${e.message}` : "could not reach the server",
    };
  }

  const { status, body } = response;

  if (status === 200 && body && typeof body === "object") {
    const b = body as { size?: number; version?: { token?: string } | null };
    return { kind: "ok", path: req.path, size: b.size ?? 0, version: b.version?.token ?? null };
  }

  if (status === 403) {
    const detail = (body as { detail?: unknown })?.detail;
    // Two shapes: the fence saying "ask", or a plain refusal (deny, or a bad approval).
    if (detail && typeof detail === "object" && (detail as { fence?: string }).fence === "ask") {
      const d = detail as { reason?: string; hint?: string };
      // The hint tells the client to go get an approval; the honest UI turns this into a dialog.
      return {
        kind: "ask", path: req.path,
        reason: d.reason ?? "this path is outside your folder",
        approval: "",
      };
    }
    const message = typeof detail === "string" ? detail : "this path cannot be written";
    return { kind: "error", path: req.path, message, retryable: false };
  }

  if (status === 409) {
    const detail = (body as { detail?: unknown })?.detail;
    if (detail && typeof detail === "object") {
      const d = detail as { current?: { token?: string } | null; yours?: string | null; reason?: string };
      return {
        kind: "conflict", path: req.path,
        current: d.current?.token ?? null,
        yours: d.yours ?? null,
        reason: d.reason ?? "somebody else changed this file",
      };
    }
    return { kind: "conflict", path: req.path, current: null, yours: null, reason: "somebody else changed this file" };
  }

  if (status === 422) {
    const detail = (body as { detail?: unknown })?.detail;
    return {
      kind: "error", path: req.path, retryable: false,
      message: typeof detail === "string" ? detail : "this path is not valid",
    };
  }

  const detail = (body as { detail?: unknown })?.detail;
  return {
    kind: "error", path: req.path, retryable: status >= 500,
    message: typeof detail === "string" ? detail : `the save failed (${status})`,
  };
}
