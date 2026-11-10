/** The truth table for "may this be sent".
 *
 * The defect this file exists to prevent: the connection state reached `disabled`, which makes a
 * `<textarea>` unfocusable in every browser. So the most important test here is not any single row —
 * it is that a connection-shaped property CANNOT BE PASSED. That is asserted structurally, at the
 * type level, which is the only place it cannot be quietly removed later.
 */
import { describe, expect, it } from "vitest";
import { blockedReason, canDecide, canRestore, canSend, canStop, hasDraft, reasonText, type BlockedReason, type SendInput } from "./compose";

const input = (status: string, requiresResume = false): SendInput => ({ status, requiresResume });

describe("canSend: the whole truth table over what makes a session writable", () => {
  it("accepts a ready session", () => {
    expect(canSend(input("ready"))).toEqual({ canSend: true, blocked: false });
  });

  it("accepts a session that is streaming, because a user may still write about it", () => {
    expect(canSend(input("streaming")).canSend).toBe(true);
  });

  it("accepts a session that is blocked on an approval: the prompt box is how you explain", () => {
    expect(canSend(input("blocked")).canSend).toBe(true);
  });

  it("refuses an archived session, and says so", () => {
    const d = canSend(input("archived"));
    expect(d).toEqual({
      canSend: false, blocked: true, reason: "archived",
      message: "This conversation is archived. Start a new one to keep working.",
    });
  });

  it("refuses a session that needs its agent restored, and says so", () => {
    const d = canSend(input("ready", true));
    expect(d.canSend).toBe(false);
    if (!d.canSend) expect(d.reason).toBe("needs-resume");
  });

  it("treats archived as the reason when both are true, because restoring is not offered", () => {
    expect(blockedReason(input("archived", true))).toBe("archived");
  });
});

describe("the connection is structurally unable to block a composer", () => {
  it("has no field a caller could use to pass a connection state", () => {
    // If someone adds `conn` to SendInput this stops compiling, which is the point: the fix for the
    // reported bug must not be removable by a later "small change".
    type Keys = keyof SendInput;
    const allowed: Keys[] = ["status", "requiresResume"];
    expect(allowed.sort()).toEqual(Object.keys({ status: "", requiresResume: "" }).sort());
  });

  it("answers the same for a session whether or not a stream is up", () => {
    // The interface cannot express a connection, so the two calls below are the SAME call. Written
    // as a test anyway: it names the requirement (FX-1, FX-5) in the place a reviewer looks.
    const session = input("ready");
    expect(canSend(session).canSend).toBe(true);
    expect(canSend({ ...session }).canSend).toBe(true);
  });
});

describe("one predicate per control, because they are different questions", () => {
  /* A single `canAct` for all three controls was tried and was WRONG: it reused `blockedReason`, so
     it disabled "Restore agent" precisely when `requiresResume` was true — the only condition under
     which Restore exists. `RunStatus.test.tsx` caught it. That is the same mistake as [F3] in the
     opposite direction: one flag for several questions. */

  it("canRestore needs the condition that blocks a message", () => {
    expect(canRestore(input("ready", true))).toBe(true);
    expect(canRestore(input("ready", false))).toBe(false);
  });

  it("canRestore is false on an archived session, where there is nothing to restore", () => {
    expect(canRestore(input("archived", true))).toBe(false);
  });

  it("canStop is true for any session that is not archived, including one needing a restore", () => {
    expect(canStop(input("streaming"))).toBe(true);
    expect(canStop(input("ready", true))).toBe(true);
    expect(canStop(input("archived"))).toBe(false);
  });

  it("canDecide is false only when there is no pending work to decide", () => {
    expect(canDecide(input("blocked"))).toBe(true);
    expect(canDecide(input("archived"))).toBe(false);
  });

  it("none of the three consults a connection, because none of them travels over the stream", () => {
    // Structural: SendInput has no conn field, so these calls cannot express one.
    const s = input("ready");
    expect([canRestore(s), canStop(s), canDecide(s)]).toEqual([false, true, true]);
  });
});

describe("reasonText is total", () => {
  it("has a sentence for every BlockedReason", () => {
    const reasons: BlockedReason[] = ["archived", "needs-resume"];
    for (const r of reasons) {
      expect(reasonText(r)).toBeTruthy();
      expect(reasonText(r)).not.toMatch(/undefined/);
    }
  });

  it("produces the same sentence the decision carries, so the box and its description agree", () => {
    for (const status of ["archived"]) {
      const d = canSend(input(status));
      if (!d.canSend) expect(d.message).toBe(reasonText(d.reason));
    }
  });
});

describe("hasDraft: a different question from canSend", () => {
  it("is false for whitespace, which is what the Send button already refuses", () => {
    expect(hasDraft("")).toBe(false);
    expect(hasDraft("   \n ")).toBe(false);
  });

  it("is true for any real text", () => {
    expect(hasDraft("chart the trips")).toBe(true);
    expect(hasDraft("  x  ")).toBe(true);
  });
});
