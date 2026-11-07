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
}

const ACL = /do not have access to (.+?)\.?$/i;
const UNREACHABLE = /cannot reach|failed to fetch|networkerror|server answered 5\d\d|\b50[234]\b|timed? ?out/i;

export function explain(message: string): Explained {
  const text = (message || "").trim();
  if (/app setting/i.test(text) && /granted/i.test(text)) {
    return {
      kind: "scope",
      title: "Your sign-in needs refreshing",
      detail: "It's not your access. This sign-in predates the app's current permissions. Sign in again: open the app in a private window, or clear this site's cookies. If it still fails, ask the app's owner to add the missing permission.",
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
