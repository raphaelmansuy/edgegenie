import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { emptySession, newTurn } from "../domain/events";
import { RunStatus } from "./RunStatus";

it("keeps failed restore actionable and explains the failure", async () => {
  const onRestore = vi.fn().mockRejectedValue(new Error("Agent history unavailable"));
  render(<RunStatus session={{ ...emptySession("s"), requiresResume: true, turns: [newTurn("t", 1)] }}
    conn={{ kind: "live" }} onRestore={onRestore} onStop={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Restore agent" }));
  await waitFor(() => expect(screen.getByText("Agent history unavailable")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Restore agent" })).toBeEnabled();
});

it("keeps Restore actionable while reconnecting, and still shows the saved conversation", () => {
  /* This test used to assert the OPPOSITE — `toBeDisabled()` while reconnecting — and that
     expectation WAS the defect (specs/012 [F3]): `const connected = conn === "live"` disabled the one
     control that gets a user out of a refused stream, and Restore in particular is needed exactly
     when the agent is detached, which is a session fact, not a connection fact. Restore is a POST, so
     a dropped event stream is not a reason to refuse it: if the request fails, the button explains
     (the test above). */
  render(<RunStatus session={{ ...emptySession("s"), requiresResume: true, turns: [newTurn("t", 1)] }}
    conn={{ kind: "reconnecting", attempt: 1, nextInMs: 1000 }} onRestore={vi.fn()} onStop={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Restore agent" })).toBeEnabled();
  expect(screen.getByText("Your progress is saved")).toBeInTheDocument();
});

it("still refuses Restore on an archived session, where there is nothing to restore", () => {
  render(<RunStatus session={{ ...emptySession("s"), status: "archived", requiresResume: true, turns: [newTurn("t", 1)] }}
    conn={{ kind: "live" }} onRestore={vi.fn()} onStop={vi.fn()} />);
  expect(screen.queryByRole("button", { name: "Restore agent" })).not.toBeInTheDocument();
});

it("does not imply failed work is still running and blocks stale archived recovery", () => {
  const failed = { ...newTurn("t", 1), status: "failed" as const, blocked: { reason: "Permission denied", missing: [], attempted: [] } };
  const { rerender } = render(<RunStatus session={{ ...emptySession("s"), status: "blocked", turns: [failed] }} conn={{ kind: "live" }} onRestore={vi.fn()} onStop={vi.fn()} />);
  expect(screen.getByText("Work failed")).toBeInTheDocument();
  expect(screen.getByText("Permission denied")).toBeInTheDocument();
  rerender(<RunStatus session={{ ...emptySession("s"), status: "archived", requiresResume: true, turns: [failed] }} conn={{ kind: "live" }} onRestore={vi.fn()} onStop={vi.fn()} />);
  expect(screen.getByText("Archived session")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Restore agent" })).not.toBeInTheDocument();
});

it("reports a rejected stop without claiming the server stopped", async () => {
  const onStop = vi.fn().mockRejectedValue(new Error("Stop request was not accepted"));
  render(<RunStatus session={{ ...emptySession("s"), status: "streaming", turns: [newTurn("t", 1)] }}
    conn={{ kind: "live" }} onRestore={vi.fn()} onStop={onStop} />);
  fireEvent.click(screen.getByRole("button", { name: "Stop work" }));
  await waitFor(() => expect(screen.getByText("Stop request was not accepted")).toBeInTheDocument());
  expect(onStop).toHaveBeenCalledTimes(1);
  expect(screen.getByText("Working on the server")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Stop work" })).toBeEnabled();
});
