/** A proposed notebook edit, shown as a decision. Pure. `[R-22]`, `[G-15]`.

 *  The gap this closes. `editor/diff.ts::minimalChange` maps a *remote edit* onto an open document; it does
 *  not propose one. So when the agent changed a notebook, the change simply appeared — the user saw an
 *  edit they never agreed to, with no way to compare it against what they had.
 *
 *  **The two hard cases, and they are the reason this module exists.**
 *
 *  1. **A dirty document.** If the user has unsaved text, applying a proposal silently destroys it. The
 *     proposal must be HELD, not applied, and say so.
 *  2. **A stale proposal.** A proposal computed against version `v3` cannot be applied to `v4` — another
 *     tab, or the agent itself, may have moved on. That is the same contract `POST /workspace/save`
 *     already uses for a version conflict (409 with both versions), reused rather than re-invented.
 *
 *  Neither case can be handled by a diff view. They are states of the *proposal*, which is why this is a
 *  type with a decision function rather than a component.
 */

export type ProposalState =
  /** Ready: the document matches the version the proposal was computed against, and is clean. */
  | "ready"
  /** The document has unsaved edits, so applying this would lose them. */
  | "held-dirty"
  /** The document moved on. The proposal has to be recomputed. */
  | "held-stale"
  /** Applied, or rejected. Terminal. */
  | "accepted"
  | "rejected";

export interface CellChange {
  /** The cell's stable key, so a reorder does not move a change onto another cell. */
  key: string;
  index: number;
  /** `replace` rewrites a cell, `insert` adds one after `index`, `delete` removes it. */
  kind: "replace" | "insert" | "delete";
  before: string;
  after: string;
  /** The agent's own words for why. An "accept" with no reason is a coin flip. */
  reason: string;
}

export interface Proposal {
  id: string;
  /** The document it belongs to, canonicalised. One proposal belongs to one notebook. */
  docId: string;
  /** The version the proposal was computed against (`objectId:size:version`). */
  version: string;
  cells: CellChange[];
  state: ProposalState;
}

export interface Decision {
  /** May `Keep` be pressed at all, and if not, why. */
  canKeep: boolean;
  canReject: boolean;
  /** What the button says when it cannot act. Empty when it can. */
  blockedReason: string;
  /** Whether pressing `Keep` should send the approval token the fence will demand. */
  needsApproval: boolean;
}

/** What the panel may do, from the proposal and the document's real state. Total over its inputs. */
export function decide(p: Proposal | null, doc: { version: string; dirty: boolean } | null): Decision {
  if (!p || !doc) {
    return { canKeep: false, canReject: false, blockedReason: "There is no proposal to decide.", needsApproval: false };
  }
  if (p.state === "accepted" || p.state === "rejected") {
    return { canKeep: false, canReject: false, blockedReason: `This proposal was already ${p.state}.`, needsApproval: false };
  }
  if (doc.dirty) {
    // The user's own text outranks the agent's suggestion: applying it would destroy work that cannot be
    // recovered from here, and the editor's undo stack does not span a programmatic replacement.
    return {
      canKeep: false, canReject: true,
      blockedReason: "You have unsaved changes. Save or discard them, then keep this proposal.",
      needsApproval: true,
    };
  }
  if (p.version !== doc.version) {
    return {
      canKeep: false, canReject: true,
      blockedReason: "This notebook changed since the proposal was made. Reject it and ask again.",
      needsApproval: true,
    };
  }
  return { canKeep: true, canReject: true, blockedReason: "", needsApproval: true };
}

/** The state a proposal is really in, from the document. Called when the document changes, so a proposal
 *  that goes stale while it is on screen says so instead of failing at the moment `Keep` is pressed. */
export function refresh(p: Proposal, doc: { version: string; dirty: boolean }): Proposal {
  if (p.state === "accepted" || p.state === "rejected") return p;
  if (doc.dirty) return { ...p, state: "held-dirty" };
  if (p.version !== doc.version) return { ...p, state: "held-stale" };
  return { ...p, state: "ready" };
}

/** What one accepted proposal does to a cell list. Pure, so "reject did not write" is a comparison of two
 *  arrays rather than a claim about a side effect. */
export function apply<T extends { key: string; source: string }>(cells: T[], changes: CellChange[]): T[] {
  const out = cells.map((c) => ({ ...c }));
  for (const ch of changes) {
    const at = out.findIndex((c) => c.key === ch.key);
    if (ch.kind === "replace" && at >= 0) {
      out[at] = { ...out[at], source: ch.after };
    } else if (ch.kind === "delete" && at >= 0) {
      out.splice(at, 1);
    } else if (ch.kind === "insert") {
      // `insert` after the cell at `index`; a key that does not exist appends, which is what a generated
      // cell at the end of a notebook means.
      const after = out.findIndex((c) => c.key === ch.key);
      const key = `proposed-${ch.key}`;
      const cell = { key, source: ch.after } as T;
      out.splice(after >= 0 ? after + 1 : out.length, 0, cell);
    }
  }
  return out;
}

/** A one-line summary for the panel header: `2 cells changed, 1 added`. */
export function summary(p: Proposal | null): string {
  if (!p || p.cells.length === 0) return "";
  const count = (k: CellChange["kind"]) => p.cells.filter((c) => c.kind === k).length;
  const bits: string[] = [];
  const changed = count("replace");
  const added = count("insert");
  const removed = count("delete");
  if (changed) bits.push(`${changed} ${changed === 1 ? "cell" : "cells"} changed`);
  if (added) bits.push(`${added} added`);
  if (removed) bits.push(`${removed} removed`);
  return bits.join(", ");
}
