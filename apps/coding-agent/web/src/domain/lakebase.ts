/** Lakebase rules, mirrored from `api/domain/lakebase.py`. Pure: no React, no fetch.
 *
 * The page and the router must agree about three things, and this is the one definition each:
 * identity (`projects/{p}` and `pg_tickets` are one object), the autoscaling arithmetic, and the
 * state words. `tests/test_lakebase_tools.py` and `domain/lakebase.test.ts` hold the two runtimes to
 * one table (spec 013 [07 §2.1], [LB-4], [LB-5]).
 */

export const MIN_CU = 0.5;
export const MAX_CU = 64;
export const MAX_SPREAD_CU = 16;
export const SCALE_TO_ZERO_MAX_CU = 32;

export const projectRef = (name: string): string => {
  const n = (name ?? "").trim().replace(/^\/+|\/+$/g, "");
  if (!n) throw new Error("a project is named by its id, for example 'pg_tickets'");
  return n.startsWith("projects/") ? n : `projects/${n}`;
};

export const projectId = (ref: string): string => projectRef(ref).split("/").pop() ?? ref;

export const branchRef = (project: string, branch = "production"): string => {
  const b = (branch || "production").trim().replace(/^\/+|\/+$/g, "");
  return b.startsWith("projects/") ? b : `${projectRef(project)}/branches/${b}`;
};

export const branchId = (ref: string): string => {
  const parts = (ref ?? "").split("/").filter(Boolean);
  const at = parts.indexOf("branches");
  if (at >= 0 && parts[at + 1]) return parts[at + 1];
  return parts[parts.length - 1] ?? "";
};

export const endpointRef = (project: string, branch = "production", endpoint = "primary"): string =>
  `${branchRef(project, branch)}/endpoints/${endpoint || "primary"}`;

/** The autoscaling rules, and the sentence that says which one was broken. */
export interface CudaRange { minCu: number; maxCu: number; scaleToZero: boolean }

export const rangeProblem = (r: CudaRange): string | null => {
  const spread = Math.round((r.maxCu - r.minCu) * 100) / 100;
  if (r.minCu < MIN_CU) return `the minimum is ${MIN_CU} CU; got ${r.minCu}`;
  if (r.maxCu > MAX_CU) return `the maximum is ${MAX_CU} CU; got ${r.maxCu}`;
  if (r.maxCu < r.minCu) return `the maximum (${r.maxCu}) is below the minimum (${r.minCu})`;
  if (spread > MAX_SPREAD_CU)
    return `max − min must not exceed ${MAX_SPREAD_CU} CU; ${r.maxCu} − ${r.minCu} = ${spread}. `
      + `Choose a maximum of at most ${r.minCu + MAX_SPREAD_CU}`;
  if (r.scaleToZero && r.maxCu > SCALE_TO_ZERO_MAX_CU)
    return `scale to zero needs a maximum of ${SCALE_TO_ZERO_MAX_CU} CU or less; got ${r.maxCu}`;
  return null;
};

export const rangeValid = (r: CudaRange): boolean => rangeProblem(r) === null;

/** What a page shows beside a range: the rule, evaluated. This is the string in wireframe S2. */
export function describeRange(r: CudaRange): string {
  const spread = Math.round((r.maxCu - r.minCu) * 100) / 100;
  return `${r.minCu} – ${r.maxCu} CU   max − min = ${spread}  ${rangeValid(r) ? "✓" : "✗"} (≤ ${MAX_SPREAD_CU})`;
}

const STATE_WORDS: Record<string, string> = {
  READY: "ready", AVAILABLE: "ready", ACTIVE: "ready",
  PROVISIONING: "starting", STARTING: "starting",
  SUSPENDED: "asleep", IDLE: "asleep", STOPPED: "stopped",
  FAILED: "failed", ERROR: "failed", DELETING: "deleting", DELETED: "deleted",
};

/** A state as a person reads it. An unknown state is returned verbatim, never guessed. */
export const stateWord = (state: string): string =>
  STATE_WORDS[(state ?? "").toUpperCase()] ?? (state ?? "").toLowerCase();

export const isReady = (state: string): boolean => stateWord(state) === "ready";
/** A suspended compute wakes on the first connection; it is a state, not a failure ([RB-7]). */
export const isSuspended = (state: string): boolean => stateWord(state) === "asleep";

/**
 * Is a project ready, given that a project has no state of its own? ([RB-12])
 *
 * The API sends a project with `status.display_name`, a version, an owner and default endpoint
 * settings — and **no state field**. Readiness belongs to the branches, and to the computes on them.
 * The page header therefore derives one word from three facts it actually has, in this order:
 *
 * 1. no branch read at all → `""`, which the header renders as the page's own load state. A guess here
 *    is how the pill said "loading" forever over a project that was ready.
 * 2. the default branch is not ready → its own state word (`starting`, `asleep`, `failed`).
 * 3. the default branch is ready but a compute on it is disabled or failed → that word.
 * 4. otherwise → `READY`.
 *
 * Suspended is deliberately **not** a failure: a compute wakes on the first connection ([RB-7]).
 * Pure and total, so the same table can be tested without a browser.
 */
export function projectState(
  branches: { name: string; state: string; isDefault: boolean }[] | { error: string } | undefined,
  compute: { state: string; suspended: boolean }[] | { error: string } | undefined,
): string {
  if (!branches || isError(branches) || branches.length === 0) return "";
  const branch = branches.find((b) => b.isDefault) ?? branches[0];
  if (!isReady(branch.state)) return branch.state;
  if (compute && !isError(compute)) {
    const broken = compute.find((c) => stateWord(c.state) === "failed" || stateWord(c.state) === "stopped");
    if (broken) return broken.state;
  }
  return "READY";
}

/** Where a project and its branch live in the Databricks UI, when the host is known. */
export function lakebaseUrl(host: string | null | undefined, project: string): string | null {
  if (!host) return null;
  const h = host.replace(/\/+$/, "");
  return `${h}/database/projects/${encodeURIComponent(projectId(project))}`;
}

export interface ProjectBlock { error?: string }

/** The four independent blocks a project page renders. Each may be an error instead of data. */
export interface LakebasePageData {
  /** [RB-12] A project carries NO `state` and NO `ready` field — see `projectState`. */
  project?: { ref: string; name: string; displayName: string;
              pgVersion?: number; defaultBranch?: string; error?: string };
  branches?: { ref: string; name: string; isDefault: boolean; state: string }[] | { error: string };
  databases?: { ref: string; name: string }[] | { error: string };
  compute?: { ref: string; name: string; type: string; state: string; suspended: boolean;
              host: string; range: string; rangeValid: boolean }[] | { error: string };
}

export const isError = (v: unknown): v is { error: string } =>
  !!v && typeof v === "object" && typeof (v as { error?: unknown }).error === "string";

/** A value that could not be read, as the page shows it: an em dash, never `0` ([UI-3], [E-11]). */
export const orDash = (v: unknown): string =>
  v === undefined || v === null || v === "" ? "—" : String(v);
