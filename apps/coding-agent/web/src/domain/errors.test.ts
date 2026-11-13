import { describe, expect, it } from "vitest";
import { explain } from "./errors";

describe("explain", () => {
  it("tells a missing app scope apart from the user's own access, and does not blame the sign-in", () => {
    const e = explain("this app has not been granted the permission it needs (`workspace`). This is an app setting, not your access: ask the app's owner to add the scope and redeploy.");
    expect(e.kind).toBe("scope");
    expect(e.title).toMatch(/missing a permission/i);
    // The deployed app offered "Sign in again" and it could not work: `postgres` is bound to the
    // app's service principal and never reaches a user token (spec 013 [RB-10]). The message must
    // point at the app, and must NOT suggest re-authenticating.
    expect(e.detail).toMatch(/not your access/i);
    expect(e.detail).toMatch(/signing in again will not change it/i);
    expect(e.detail).not.toMatch(/sign in again to get/i);
    expect(e.action).toBeUndefined();
    expect(e.retryable).toBe(false);
  });

  it("names the path on an ACL denial, and calls the root by its name", () => {
    expect(explain("you do not have access to /Shared/finance")).toMatchObject({
      kind: "acl", title: "You don't have access", detail: "to /Shared/finance. Ask its owner to share it with you.",
    });
    expect(explain("you do not have access to /").detail).toMatch(/the workspace root/);
  });

  it("marks only transient failures as retryable", () => {
    expect(explain("cannot reach the workspace: Failed to fetch")).toMatchObject({ kind: "unreachable", retryable: true });
    expect(explain("/api/2.0/x failed (502): bad gateway").kind).toBe("unreachable");
    expect(explain("you do not have access to /x").retryable).toBe(false);
  });

  it("never returns an empty explanation", () => {
    expect(explain("")).toMatchObject({ kind: "other", detail: "No details were returned." });
    expect(explain("boom")).toMatchObject({ kind: "other", detail: "boom", retryable: true });
  });
});
