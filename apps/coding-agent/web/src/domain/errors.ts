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
    // The server names the scope when it knows it (`ScopeMissing` carries `scopes`). Naming it is
    // the difference between "sign in again" and "sign in again, and this is what you were missing",
    // and on the deployed app the names were absent so the user had to guess (spec 013 [RB-2]).
    const named = /\(`([^`]+)`\)/.exec(text)?.[1]?.trim();
    return {
      kind: "scope",
      title: "Your sign-in needs refreshing",
      detail: named
        ? `The app now has the \`${named}\` permission. This browser session signed in before it was granted, so its token does not carry it. Sign in again to get a token with the current permissions; if it still fails, ask the app's owner to check the app's scopes.`
        : "It's not your access. This sign-in predates the app's current permissions. Sign in again to get a token with the current permissions; if it still fails, ask the app's owner to check the app's scopes.",
      retryable: false,
      action: { label: "Sign in again", href: "/.auth/logout" },
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
