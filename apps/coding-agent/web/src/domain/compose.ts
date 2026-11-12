/** Compose: may this be sent, and if not, why?
 *
 * ONE answer to ONE question. Before this module the question had four implementations
 * (`AssistantDock`, the main composer in `App`, `RunStatus`, and the approval list), and two of them
 * disagreed about the same session. The reported defect — "I cannot focus on the right panel to edit
 * and ask a new command" — came from one of them feeding the connection state into `disabled`, which
 * makes a `<textarea>` unfocusable in every browser (measured; see specs/012-uy 02 §3).
 *
 * Two rules this file exists to enforce, both structural rather than by convention:
 *
 *   1. THE CONNECTION IS NOT AN INPUT. `SendInput` has no `conn` field, so a call site cannot
 *      disable the composer because the stream is down. Losing the stream means "the answer will not
 *      arrive yet", not "you may not ask": the send is an HTTP POST with an idempotency key and the
 *      turn survives on the server (spec 010). Anything else contradicts the durability the rest of
 *      the system exists to provide.
 *
 *   2. A REFUSAL NAMES ITS REASON. `SendDecision` is a tagged union, not a boolean, so the caller
 *      cannot forget to say why. The wording lives here so the dock, the main composer and the
 *      `aria-describedby` element say the same sentence.
 *
 * Pure: no React, no DOM, no storage. See specs/012-ux-improve 07 §1.
 */

/** Why a composer cannot be written into. Archived and needs-resume are the only two states that
 *  make a session genuinely unwritable; both are server facts, not connection facts. */
export type BlockedReason = "archived" | "needs-resume";
/** What a decision needs to know. Deliberately tiny (spec 07, interface segregation): it does not
 *  take a whole `SessionView` and it does not take a `Conn`. */
export interface SendInput {
  /** `SessionView.status`: "ready" | "streaming" | "provisioning" | "blocked" | "archived" | … */
  status: string;
  /** The server says the agent is not attached and must be restored before work can continue. */
  requiresResume?: boolean;
}

export type SendDecision =
  | { canSend: true; blocked: false }
  | { canSend: false; blocked: true; reason: BlockedReason; message: string };

/** The one place a blocked reason becomes words. Total over `BlockedReason`: adding a reason without
 *  a sentence is a type error, which is why this is a `Record` and not an `if` chain. */
const MESSAGE: Record<BlockedReason, string> = {
  archived: "This conversation is archived. Start a new one to keep working.",
  "needs-resume": "Restore the agent to continue this conversation.",
};

export const reasonText = (reason: BlockedReason): string => MESSAGE[reason];

/** The reason a session is unwritable, or null when it is writable. Ordered: archived wins, because
 *  restoring an archived session is not offered and the user should be told the simpler truth. */
export function blockedReason(input: SendInput): BlockedReason | null {
  if (input.status === "archived") return "archived";
  if (input.requiresResume) return "needs-resume";
  return null;
}

/** May this composer accept text? Note what is NOT consulted: the connection, the pending approval
 *  list, whether the agent is streaming. All three are things a user may still write about. */
export function canSend(input: SendInput): SendDecision {
  const reason = blockedReason(input);
  if (reason === null) return { canSend: true, blocked: false };
  return { canSend: false, blocked: true, reason, message: MESSAGE[reason] };
}

/** May a *control* act? This is NOT one question, and pretending it was is the same mistake the
 *  composer made. Each control asks something different:
 *
 *    Restore  needs the very condition that blocks a message (requires-resume). A single
 *             `canAct` that reused `blockedReason` disabled Restore precisely when it was needed —
 *             caught by `RunStatus.test.tsx`, which asserts Restore is actionable after a failure.
 *    Stop     is a POST; it needs a live *session*, not a live *stream*.
 *    Decide   is a POST for pending work; an archived session has none.
 *
 *  So there is one predicate per control, each stating its own condition. `[F3]` was the opposite
 *  error: one flag (`conn === "live"`) answering all three, and answering them wrongly. */

/** Restore is offered exactly when the agent is detached and the session is not archived. */
export const canRestore = (input: SendInput): boolean =>
  Boolean(input.requiresResume) && input.status !== "archived";

/** Stop is offered on any session that is not archived: the request goes over HTTP, so a dropped
 *  event stream is not a reason to refuse it. */
export const canStop = (input: SendInput): boolean => input.status !== "archived";

/** An approval decision is a POST for pending work. Archived means there is none. */
export const canDecide = (input: SendInput): boolean => input.status !== "archived";

/** Whether there is anything to send. Separate from `canSend` because they are different questions:
 *  the box may be writable while the send button is not, and the original defect hid behind their
 *  sharing one flag. */
export const hasDraft = (draft: string): boolean => draft.trim().length > 0;
