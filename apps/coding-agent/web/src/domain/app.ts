/** Databricks Apps, as a page reads them. Pure: mirrored from `api/adapters/databricks/apps.py`.
 *
 * The one question this module answers is the user's: **is it working?** A deployment's `SUCCEEDED`
 * means the process started, which is not the same thing — this repository learned that when
 * `make deploy` reported success three times while serving none of the work. So the answer is an HTTP
 * status, and a cold start is its own state (spec 013 [AP-4], [UI-4], [E-14]).
 */

export type AppState = "running" | "starting" | "stopped" | "deploying" | "failing" | "unknown";
export type HealthState = "running" | "starting" | "failing" | "unreachable" | "unknown";

export interface AppResource {
  name: string;
  kind: string;
  permission: string;
  branch: string;
}

export interface AppHealth {
  status: number | null;
  ms: number;
  state: HealthState;
  url?: string;
  logs?: string;
  detail?: string;
  checkedAt?: string;
}

export interface AppView {
  name: string;
  url: string;
  state: AppState | string;
  stateRaw: string;
  lakebase: string;
  resources: AppResource[];
  creator: string;
  computeSize?: string;
  deploymentState?: string;
  servicePrincipal?: string;
  health?: AppHealth;
}

const APP_WORDS: Record<string, AppState> = {
  RUNNING: "running", STOPPED: "stopped", CRASHED: "failing",
  DEPLOYING: "deploying", UNAVAILABLE: "starting", PENDING: "starting",
};

export const appStateWord = (state: string): string =>
  APP_WORDS[(state ?? "").toUpperCase()] ?? (state ?? "").toLowerCase();

/** A state's tone, so a page can colour it without inventing a second vocabulary. */
export function tone(state: string): "good" | "busy" | "bad" | "quiet" {
  switch (state) {
    case "running": return "good";
    case "starting": case "deploying": return "busy";
    case "failing": return "bad";
    default: return "quiet";
  }
}

/** What the page says about health, in one sentence, including the case where it could not tell. */
export function healthSentence(h: AppHealth | undefined, state: string): string {
  if (!h) return state === "running" ? "No health check taken yet." : "No health check taken yet.";
  switch (h.state) {
    case "running": return `Answered ${h.status} in ${h.ms} ms`;
    case "starting": return `Cold start: no answer in ${Math.round(h.ms / 1000)} s, which is normal after the app was idle`;
    case "failing": return `Answered ${h.status} — the app is up and returning an error`;
    case "unreachable": return `Could not reach the app${h.detail ? ` (${h.detail})` : ""}`;
    default: return "Health unknown: the check did not run";
  }
}

export const logsUrl = (url: string): string | null =>
  !url ? null : `${url.replace(/\/+$/, "")}/logz`;

/** The app's Lakebase resource, when it has one. `[F6]`: without it the app cannot connect. */
export function postgresResource(a: AppView | null | undefined): AppResource | null {
  return a?.resources.find((r) => r.kind === "postgres") ?? null;
}

/** The apps that use a project. One pass: the list payload already carries the resource ([06 §6.2]). */
export const usingProject = <T extends { lakebase: string }>(apps: T[], project: string): T[] =>
  project ? apps.filter((a) => a.lakebase === project) : [];

/** The prompt the "ask the agent to fix it" action sends. It carries what the page knows, so the
 *  agent does not have to rediscover it — and the status code, which is the one fact that narrows a
 *  500 ([E-13]). */
export function fixPrompt(a: AppView): string {
  const h = a.health;
  const parts = [
    `The Databricks App \`${a.name}\` is ${a.state}${h?.status ? ` and returned HTTP ${h.status}` : ""}.`,
    "Read its logs at " + (logsUrl(a.url) ?? "the app's /logz") + ",",
    "find the cause, fix the app's source in my working folder, redeploy it,",
    "and prove it answers by running a health check.",
  ];
  return parts.join(" ");
}
