/**
 * What a failed workspace call means, in words a user can act on. Pure, so it is tested.
 *
 * The server already says the right thing (`ScopeMissing` vs a plain denial); this module only
 * decides how to *present* it. The distinction is the point: "you do not have access" sends the user
 * to the object's owner, "this app has not been granted…" sends them to the app's owner, and showing
 * the wrong one cost a real session.
 */

export type ErrorKind = "scope" | "acl" | "unreachable" | "other";

export interface Explained {
  kind: ErrorKind;
  /** One short line: what happened. */
  title: string;
  /** What to do, or what the platform said. */
  detail: string;
  /** Retrying can help: a transient failure, not a refusal. */
  retryable: boolean;
  /**
   * A link that actually fixes it. The message told the user to "open a private window or clear
   * this site's cookies", which is a bad instruction: it asks them to understand cookies and to lose
   * every other session on the machine. `/.auth/logout` on the app redirects straight back into a
   * fresh OAuth authorize with `approval_prompt=consent` (measured), which re-issues the token with
   * the permissions as they are NOW — the one thing that resolves a stale sign-in.
   */
  action?: { label: string; href: string };
}

const ACL = /do not have access to (.+?)\.?$/i;
const UNREACHABLE = /cannot reach|failed to fetch|networkerror|server answered 5\d\d|\b50[234]\b|timed? ?out/i;

export function explain(message: string): Explained {
  const text = (message || "").trim();
  if (/app setting/i.test(text) && /granted/i.test(text)) {
    // The app names the scope when the platform does (`ScopeMissing` carries `scopes`).
    //
    // There is deliberately NO action here. An earlier version offered "Sign in again", and the
    // deployed app proved it a dead end: `postgres` is bound to the app's service principal and can
    // never appear in a user token, so re-authenticating changes nothing (spec 013 [RB-10]). The
    // fix is on the app side, so the only honest thing to say is who can make it.
    const named = /\(`([^`]+)`\)/.exec(text)?.[1]?.trim();
    return {
      kind: "scope",
      title: "This app is missing a permission",
      detail: named
        ? `The app has not been granted \`${named}\`. This is an app setting, not your access, and signing in again will not change it: ask whoever owns this deployment to grant the scope and redeploy.`
        : "This is an app setting, not your access. Ask whoever owns this deployment to grant the missing scope and redeploy.",
      retryable: false,
    };
  }
  const acl = ACL.exec(text);
  if (acl) {
    const where = acl[1] === "/" ? "the workspace root" : acl[1];
    return {
      kind: "acl",
      title: "You don't have access",
      detail: `to ${where}. Ask its owner to share it with you.`,
      retryable: false,
    };
  }
  if (UNREACHABLE.test(text)) {
    return {
      kind: "unreachable",
      title: "Can't reach the workspace",
      detail: "This is usually temporary.",
      retryable: true,
    };
  }
  return { kind: "other", title: "Something went wrong", detail: text || "No details were returned.", retryable: true };
}
