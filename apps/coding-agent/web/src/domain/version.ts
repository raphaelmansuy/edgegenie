/** Which build this is, in one place, so every surface states it identically.
 *
 * The values are compiled in by `vite.config.ts`. They come from `apps/coding-agent/VERSION`, the same
 * file the API answers `/api/version` from — which is what lets `scripts/verify-deployed.sh` prove
 * that the bundle a browser loaded belongs to the server it talks to.
 *
 * Two sources exist on purpose:
 *   - these constants answer instantly, and answer even when the API is unreachable;
 *   - `api.version()` carries the COMMIT the platform resolved, which a Workspace-folder deployment
 *     cannot compile in because it has no `.git`.
 * The UI prefers the live answer and falls back to the compiled one, so it never shows `vundefined`.
 */

/** Where a reader goes next: the site, the source, the release history. Shared with the API. */
export const DOCS_URL = "https://raphaelmansuy.github.io/opengenie/";
export const SOURCE_URL = "https://github.com/raphaelmansuy/opengenie";
export const RELEASES_URL = `${SOURCE_URL}/releases`;

export interface BuildFacts {
  /** `1.0.0`, or `unknown` when the tree shipped no readable `VERSION`. */
  version: string;
  /** The resolved commit, short, or empty when the deployment has none to report. */
  commit: string;
  /** ISO timestamp of this bundle's build. */
  built: string;
}

export const COMPILED: BuildFacts = {
  version: typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : "unknown",
  commit: typeof __APP_COMMIT__ === "string" ? __APP_COMMIT__ : "",
  built: typeof __APP_BUILT__ === "string" ? __APP_BUILT__ : "",
};

/** The label a person reads: `v1.0.0` when there is no commit, `v1.0.0 · abc1234` when there is. */
export function versionLabel(facts: BuildFacts = COMPILED): string {
  const head = `v${facts.version}`;
  return facts.commit ? `${head} · ${facts.commit.slice(0, 7)}` : head;
}

/** The `title` for a version chip: what it is, when it was built, and why the commit may be absent. */
export function versionTitle(facts: BuildFacts = COMPILED): string {
  const lines = [`OpenGenie ${versionLabel(facts)}`];
  if (facts.built) {
    const when = new Date(facts.built);
    if (!Number.isNaN(when.getTime())) lines.push(`built ${when.toISOString().slice(0, 16).replace("T", " ")} UTC`);
  }
  lines.push(facts.commit ? "commit the platform resolved" : "no commit reported by this deployment");
  return lines.join(" — ");
}

/** Merge the server's answer over the compiled facts. A server value wins; an absent one does not
 *  erase what the bundle knows, because "the deployment does not report a commit" and "this build
 *  has no commit" are different statements and only the server can make the first. */
export function withServer(facts: BuildFacts, server?: Partial<BuildFacts> | null): BuildFacts {
  if (!server) return facts;
  return {
    version: server.version || facts.version,
    commit: server.commit || facts.commit,
    built: facts.built,
  };
}
