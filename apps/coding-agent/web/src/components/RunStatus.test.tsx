import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { emptySession, newTurn } from "../domain/events";
import { RunStatus } from "./RunStatus";

it("keeps failed restore actionable and explains the failure", async () => {
  const onRestore = vi.fn().mockRejectedValue(new Error("Agent history unavailable"));
  render(<RunStatus session={{ ...emptySession("s"), requiresResume: true, turns: [newTurn("t", 1)] }}
    conn="live" onRestore={onRestore} onStop={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Restore agent" }));
  await waitFor(() => expect(screen.getByText("Agent history unavailable")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Restore agent" })).toBeEnabled();
});

it("disables remote actions while offline without hiding the saved conversation", () => {
  render(<RunStatus session={{ ...emptySession("s"), requiresResume: true, turns: [newTurn("t", 1)] }}
    conn="lost" onRestore={vi.fn()} onStop={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Restore agent" })).toBeDisabled();
  expect(screen.getByText("Your progress is saved")).toBeInTheDocument();
});
