/** The Data pane's failure handling, tested without a browser.
 *
 * Both rules here came from the deployed app: the same "sign-in needs refreshing" box appeared
 * TWICE (one per failed call), and the box did not say which permission was missing even though the
 * server had said so.
 */
import { render, screen } from "@testing-library/react";
import { DataTree, errorBoxes } from "./DataTree";
import { explain } from "../domain/errors";

const SCOPE_MESSAGE =
  "this app has not been granted the permission it needs (`postgres`). This is an app setting, "
  + "not your access. If you signed in before the app's permissions changed, sign in again; "
  + "otherwise ask the app's owner to add the scope and redeploy.";

describe("errorBoxes", () => {
  it("shows ONE box when two calls fail for the same reason", () => {
    // The screenshot of the deployed app: /api/lakebase/projects and /api/apps both 403, two boxes.
    const boxes = errorBoxes(
      { state: "error", error: SCOPE_MESSAGE },
      { state: "error", error: SCOPE_MESSAGE },
    );
    expect(boxes).toHaveLength(1);
  });

  it("keeps two boxes when the reasons differ", () => {
    // Two distinct faults are two things to fix.
    const boxes = errorBoxes(
      { state: "error", error: "you do not have access to /Shared" },
      { state: "error", error: "can't reach the workspace" },
    );
    expect(boxes).toHaveLength(2);
  });

  it("ignores a load that succeeded or is still loading", () => {
    expect(errorBoxes({ state: "ready" }, { state: "loading" }, { state: "error", error: "x" }))
      .toEqual(["x"]);
    expect(errorBoxes({ state: "ready" }, { state: "loading" })).toEqual([]);
  });
});

describe("the sign-in message names what was missing", () => {
  it("names the scope the server reported", () => {
    // [RB-2] the server already says `postgres`; the page must not throw that away.
    const e = explain(SCOPE_MESSAGE);
    expect(e.kind).toBe("scope");
    expect(e.title).toBe("Your sign-in needs refreshing");
    expect(e.detail).toContain("postgres");
    expect(e.retryable).toBe(false);
  });

  it("still explains itself when the scope is not named", () => {
    const e = explain("this app has not been granted the permission it needs. This is an app setting, not your access.");
    expect(e.kind).toBe("scope");
    expect(e.detail).toMatch(/sign in again/i);
    expect(e.retryable).toBe(false);
  });
});

describe("the Data pane on a refusal", () => {
  const json = (body: unknown, status = 200) => ({
    ok: status < 400, status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  });

  it("renders one box, not two, when both reads are refused", async () => {
    globalThis.fetch = vi.fn(async () => json({ detail: SCOPE_MESSAGE }, 403)) as unknown as typeof fetch;
    render(<DataTree selected={null} onOpen={() => {}} />);
    const found = await screen.findAllByText(/sign-in needs refreshing/i);
    expect(found).toHaveLength(1);
  });

  it("offers no retry for a permission wall", async () => {
    globalThis.fetch = vi.fn(async () => json({ detail: SCOPE_MESSAGE }, 403)) as unknown as typeof fetch;
    render(<DataTree selected={null} onOpen={() => {}} />);
    await screen.findAllByText(/sign-in needs refreshing/i);
    // PaneError only draws the retry when the failure is retryable.
    expect(screen.queryByRole("button", { name: /Try again/i })).not.toBeInTheDocument();
  });

  it("offers a real sign-in action instead of telling the user to clear cookies", async () => {
    // The deployed app said "clear this site's cookies", which asks the user to lose every other
    // session. `/.auth/logout` re-authorises with the current permissions (measured).
    globalThis.fetch = vi.fn(async () => json({ detail: SCOPE_MESSAGE }, 403)) as unknown as typeof fetch;
    render(<DataTree selected={null} onOpen={() => {}} />);
    const link = await screen.findByRole("link", { name: /sign in again/i });
    expect(link).toHaveAttribute("href", "/.auth/logout");
  });
});
