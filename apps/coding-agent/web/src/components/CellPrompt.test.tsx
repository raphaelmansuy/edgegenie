import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CellPrompt } from "./CellPrompt";
import { CellInsert } from "./CellInsert";
import { CellOutput } from "./CellOutput";
import { CELL_INTENTS } from "../domain/cellprompt";

afterEach(cleanup);

describe("CellPrompt", () => {
  it("takes focus, sends on Enter, and never sends an empty instruction", () => {
    const onSend = vi.fn();
    render(<CellPrompt mode="edit" label="cell 3" onSend={onSend} onClose={() => {}} />);
    const box = screen.getByRole("textbox", { name: "Instruction for cell 3" });
    expect(document.activeElement).toBe(box);
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: "  use a join  " } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("use a join");
  });

  it("Shift+Enter is a line break, not a send", () => {
    const onSend = vi.fn();
    render(<CellPrompt mode="edit" label="cell 1" onSend={onSend} onClose={() => {}} />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "a" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("Escape closes without sending and does not leak to the page", () => {
    const onClose = vi.fn(); const onSend = vi.fn(); const outer = vi.fn();
    render(<div onKeyDown={outer}><CellPrompt mode="edit" label="cell 1" onSend={onSend} onClose={onClose} /></div>);
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
    expect(outer).not.toHaveBeenCalled();
  });

  it("a quick action sends its instruction in one click", () => {
    const onSend = vi.fn();
    render(<CellPrompt mode="edit" label="cell 2" onSend={onSend} onClose={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Fix" }));
    expect(onSend).toHaveBeenCalledWith(CELL_INTENTS.find((i) => i.id === "fix")!.instruction);
  });

  it("an insert prompt has no quick actions, which describe an existing cell", () => {
    render(<CellPrompt mode="insert" label="after cell 2" onSend={() => {}} onClose={() => {}} />);
    expect(screen.queryByRole("group", { name: "Quick actions" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "Describe the new cell after cell 2" })).toBeTruthy();
  });

  it("offers Discuss only when the app can open the conversation", () => {
    const { rerender } = render(<CellPrompt mode="edit" label="cell 1" onSend={() => {}} onClose={() => {}} />);
    expect(screen.queryByText("Discuss in the assistant")).toBeNull();
    const onDiscuss = vi.fn();
    rerender(<CellPrompt mode="edit" label="cell 1" onSend={() => {}} onClose={() => {}} onDiscuss={onDiscuss} />);
    fireEvent.click(screen.getByText("Discuss in the assistant"));
    expect(onDiscuss).toHaveBeenCalled();
  });
});

describe("CellInsert", () => {
  it("names its position in words and routes each button", () => {
    const [code, text, agent] = [vi.fn(), vi.fn(), vi.fn()];
    render(<CellInsert after={2} total={4} onCode={code} onText={text} onAgent={agent} />);
    expect(screen.getByRole("group", { name: "Add a cell after cell 2" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /after cell 2: code/ }));
    fireEvent.click(screen.getByRole("button", { name: /after cell 2: text/ }));
    fireEvent.click(screen.getByRole("button", { name: /after cell 2: generate with the agent/ }));
    expect([code, text, agent].map((f) => f.mock.calls.length)).toEqual([1, 1, 1]);
  });

  it("offers no Generate when there is no agent to send it to", () => {
    render(<CellInsert after={4} total={4} onCode={() => {}} onText={() => {}} />);
    expect(screen.queryByRole("button", { name: /generate/ })).toBeNull();
    expect(screen.getByRole("group", { name: "Add a cell at the end" })).toBeTruthy();
  });
});

describe("CellOutput fix", () => {
  const failed = { state: "failed" as const, seconds: 1, error: "[TABLE_OR_VIEW_NOT_FOUND] x" };
  it("a failed run offers the fix, and a successful one does not", () => {
    const onFix = vi.fn();
    const { rerender } = render(<CellOutput run={failed} onClear={() => {}} onFix={onFix} />);
    fireEvent.click(screen.getByRole("button", { name: /Fix with agent/ }));
    expect(onFix).toHaveBeenCalled();
    rerender(<CellOutput run={{ state: "succeeded", seconds: 1, columns: ["a"], rows: [["1"]] }} onClear={() => {}} onFix={onFix} />);
    expect(screen.queryByRole("button", { name: /Fix with agent/ })).toBeNull();
  });

  it("without an agent to send to there is no fix button", () => {
    render(<CellOutput run={failed} onClear={() => {}} />);
    expect(screen.queryByRole("button", { name: /Fix with agent/ })).toBeNull();
  });
});
