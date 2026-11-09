import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { emptySession, newTurn, type SessionView, type Turn } from "../domain/events";
import { MissionScreen } from "./MissionScreen";

const accomplished: Turn = { ...newTurn("old", 1, "Build the monthly report", "past/model"), status: "completed", answer: "A reviewable report.",
  tools: [{ callId: "c1", name: "write_notebook", status: "completed", args: '{"path":"/Shared/report"}', summary: "Saved report" }],
  evidence: [{ requirement: "Write report", toolCallId: "c1", tool: "write_notebook", summary: "Saved", verified: true }] };
const current = newTurn("current", 2, "Check the revenue pipeline", "current/model");
const base: SessionView = { ...emptySession("s"), status: "streaming", folder: "/Shared", turns: [accomplished, current] };
const props = { conn: "live", dockVisible: true, onOpen: vi.fn(), onConversation: vi.fn(), onStop: vi.fn(), onRestore: vi.fn() };

describe("MissionScreen", () => {
  it("navigates last achieved and current without sending or losing the history pin on updates", () => {
    const { rerender } = render(<MissionScreen {...props} session={base} />);
    expect(screen.getByRole("heading", { name: current.prompt })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Last achieved" }));
    expect(screen.getByRole("heading", { name: accomplished.prompt })).toBeInTheDocument();
    rerender(<MissionScreen {...props} session={{ ...base, turns: [...base.turns, { ...newTurn("queue", 3), status: "queued" }] }} />);
    expect(screen.getByRole("heading", { name: accomplished.prompt })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Return to current mission" }));
    expect(screen.getByRole("heading", { name: current.prompt })).toBeInTheDocument();
  });
  it("provides keyboard tabs and full selected-turn activity", () => {
    render(<MissionScreen {...props} session={base} />);
    const overview = screen.getByRole("tab", { name: "Overview" });
    fireEvent.keyDown(overview, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: /Activity/ })).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveTextContent(current.prompt);
    expect(screen.getByRole("tabpanel")).not.toHaveTextContent(accomplished.prompt);
    fireEvent.keyDown(screen.getByRole("tab", { name: /Activity/ }), { key: "Home" });
    expect(overview).toHaveFocus(); expect(overview).toHaveAttribute("aria-selected", "true");
  });
  it("opens per-turn outputs and exposes exact evidence source", () => {
    const onOpen = vi.fn();
    render(<MissionScreen {...props} onOpen={onOpen} session={{ ...base, turns: [accomplished] }} />);
    fireEvent.click(screen.getByRole("button", { name: /report Written/ }));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ ref: "/Shared/report", kind: "notebook" }));
    const proof = screen.getByText("Write report").closest("details")!;
    fireEvent.click(within(proof).getByText("Write report"));
    expect(within(proof).getByRole("button", { name: /wrote a notebook completed/ })).toBeInTheDocument();
  });
  it("flags missing sources and incomplete plans without inventing success", () => {
    const t = { ...accomplished, tools: [], plan: [{ content: "Unfinished work", status: "unknown" }] };
    render(<MissionScreen {...props} session={{ ...base, turns: [t] }} />);
    expect(screen.getByText("Ready for review")).toBeInTheDocument();
    expect(screen.getByText("0 of 1 verified")).toBeInTheDocument();
    expect(screen.getByText("unknown")).toBeInTheDocument();
    expect(screen.getByText(/turn ended before/)).toBeInTheDocument();
    expect(screen.getByText(/No source tool call/)).toBeInTheDocument();
  });
  it("keeps empty and offline states useful and mutations disabled", () => {
    const { rerender } = render(<MissionScreen {...props} session={{ ...base, turns: [] }} />);
    expect(screen.getByRole("combobox", { name: "Choose mission" })).toBeDisabled();
    rerender(<MissionScreen {...props} dockVisible={false} conn="lost" session={base} />);
    expect(screen.getByText(/Updates paused/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Stop work" })).toBeDisabled();
  });
  it("keeps full multiline objectives and large answers readable", () => {
    const t = { ...accomplished, prompt: "Long request ".repeat(20) + "\nsecond line", answer: "x".repeat(40_001) };
    render(<MissionScreen {...props} session={{ ...base, turns: [t] }} />);
    expect(screen.getByText("Full request")).toBeInTheDocument();
    expect(screen.getByText(/second line/)).toBeInTheDocument();
    expect(screen.getByText(t.answer)).toHaveClass("streaming-plain");
  });
  it("falls back when a selected turn disappears from the session", () => {
    const { rerender } = render(<MissionScreen {...props} session={base} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "old" } });
    rerender(<MissionScreen {...props} session={{ ...base, turns: [current] }} />);
    expect(screen.getByRole("heading", { name: current.prompt })).toBeInTheDocument();
  });
});
