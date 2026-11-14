import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Composer } from "./Composer";
import { api } from "../api/client";
import { TreeRow, treeKeys } from "./Tree";
import { makeDoc } from "../domain/docs";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const base = {
  busy: false, onStop: () => {}, attachments: [], onAdd: () => {}, onRemove: () => {}, openDocs: [],
};

describe("Composer context", () => {
  it("retains submission feedback and the failed request when a drawer mounts a new composer", async () => {
    const props = { ...base, onSend: async () => {} };
    const first = render(<Composer {...props} delivery={{ state: "sending", text: "Inspect sales" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Sending mission");
    expect(screen.getByRole("textbox")).toHaveValue("Inspect sales");
    first.unmount();
    const next = render(<Composer {...props} delivery={{ state: "sending", text: "Inspect sales" }} />);
    expect(screen.getByRole("button", { name: "Sending…" })).toBeDisabled();
    next.rerender(<Composer {...props} delivery={{ state: "failed", text: "Inspect sales", error: "Permission denied" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Permission denied");
    expect(screen.getByRole("textbox")).toHaveValue("Inspect sales");
  });

  it("acknowledges immediately, prevents repeat sends, and confirms server acceptance", async () => {
    let accept!: () => void;
    const onSend = vi.fn(() => new Promise<void>(resolve => { accept = resolve; }));
    render(<Composer {...base} onSend={onSend} />);
    const box = screen.getByRole("textbox", { name: "Message the agent" });
    fireEvent.change(box, { target: { value: "Build a report" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(screen.getByRole("status")).toHaveTextContent("Sending mission");
    expect(screen.getByRole("button", { name: "Sending…" })).toBeDisabled();
    expect(box).toHaveValue("Build a report");
    expect(box).toHaveAttribute("aria-busy", "true");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(1);
    await act(async () => accept());
    expect(box).toHaveValue("");
    expect(screen.getByRole("status")).toHaveTextContent("Mission accepted");
  });

  it("explains a slow submission and retains the draft after refusal", async () => {
    vi.useFakeTimers();
    try {
      let reject!: (e: Error) => void;
      render(<Composer {...base} onSend={() => new Promise<void>((_, fail) => { reject = fail; })} />);
      const box = screen.getByRole("textbox", { name: "Message the agent" });
      fireEvent.change(box, { target: { value: "Inspect sales" } });
      fireEvent.keyDown(box, { key: "Enter" });
      act(() => vi.advanceTimersByTime(8000));
      expect(screen.getByRole("status")).toHaveTextContent("Still sending");
      await act(async () => reject(new Error("Permission denied")));
      expect(screen.getByRole("alert")).toHaveTextContent("Permission denied");
      expect(box).toHaveValue("Inspect sales");
      expect(box).not.toHaveAttribute("readonly");
      expect(screen.queryByRole("status")).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it("does not submit the Enter that commits IME text", () => {
    const onSend = vi.fn();
    render(<Composer {...base} onSend={onSend} />);
    const box = screen.getByRole("textbox", { name: "Message the agent" });
    fireEvent.change(box, { target: { value: "分析" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("offers Send for a follow-up draft while a mission is running", () => {
    render(<Composer {...base} busy onSend={async () => {}} />);
    expect(screen.getByRole("button", { name: /Stop/ })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Also check revenue" } });
    expect(screen.getByRole("button", { name: /Send/ })).toBeEnabled();
  });
  it("offers open documents when you type @ and adds the chosen one", async () => {
    const onAdd = vi.fn();
    const docs = [makeDoc("notebook", "/Users/a/taxi_hours"), makeDoc("table", "main.s.orders")];
    render(<Composer {...base} openDocs={docs} onAdd={onAdd} onSend={async () => {}} />);
    const box = screen.getByRole("textbox", { name: "Message the agent" }) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "look at @tax", selectionStart: 12 } });
    box.setSelectionRange(12, 12);
    fireEvent.select(box);
    const opt = await screen.findByRole("option", { name: /taxi_hours/ });
    fireEvent.mouseDown(opt);
    expect(onAdd).toHaveBeenCalledWith({ kind: "notebook", ref: "/Users/a/taxi_hours", name: "taxi_hours" });
    await waitFor(() => expect(box.value.trim()).toBe("look at"));
  });

  it("searches the workspace for a two-letter query and shows what it found", async () => {
    vi.spyOn(api, "search").mockResolvedValue({ root: "/", complete: true,
      results: [{ path: "/Users/a/sales_report", name: "sales_report", kind: "notebook" },
        { path: "/Users/a/sales", name: "sales", kind: "directory" }] });
    render(<Composer {...base} onSend={async () => {}} />);
    const box = screen.getByRole("textbox", { name: "Message the agent" }) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "@sa", selectionStart: 3 } });
    box.setSelectionRange(3, 3);
    fireEvent.select(box);
    expect(await screen.findByRole("option", { name: /sales_report/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /^sales\b(?!_)/ })).toBeNull();   // folders are not attachable here
  });

  it("shows chips, marks the open document, and lets you remove an explicit one", () => {
    const onRemove = vi.fn();
    const a = { kind: "table" as const, ref: "main.s.orders", name: "main.s.orders" };
    render(<Composer {...base} attachments={[a]} auto={{ kind: "notebook", ref: "/x/nb", name: "nb" }}
      onRemove={onRemove} onSend={async () => {}} />);
    expect(screen.getByText("open")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove main.s.orders" }));
    expect(onRemove).toHaveBeenCalledWith(a);
  });

  it("sends the trimmed text with Cmd+Enter and clears the box", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<Composer {...base} onSend={onSend} />);
    const box = screen.getByRole("textbox", { name: "Message the agent" }) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: "  hello  " } });
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    await waitFor(() => expect(onSend).toHaveBeenCalledWith("hello", []));
    await waitFor(() => expect(box.value).toBe(""));
  });
});

describe("Tree keyboard", () => {
  const Tree = () => (
    <div role="tree">
      {["a", "b", "c"].map((n) => (
        <TreeRow key={n} depth={0} caret={false} icon="file" iconClass="" name={n} onActivate={() => {}} onKeyDown={treeKeys} />
      ))}
    </div>
  );
  it("ArrowDown/ArrowUp/End/Home move focus between rows", () => {
    render(<Tree />);
    const rows = screen.getAllByRole("treeitem");
    rows[0].focus();
    fireEvent.keyDown(rows[0], { key: "ArrowDown" });
    expect(document.activeElement).toBe(rows[1]);
    fireEvent.keyDown(rows[1], { key: "End" });
    expect(document.activeElement).toBe(rows[2]);
    fireEvent.keyDown(rows[2], { key: "ArrowUp" });
    expect(document.activeElement).toBe(rows[1]);
    fireEvent.keyDown(rows[1], { key: "Home" });
    expect(document.activeElement).toBe(rows[0]);
  });
  it("a key pressed inside a row's action button does not activate the row", () => {
    const onActivate = vi.fn(); const run = vi.fn();
    render(<div role="tree"><TreeRow depth={0} caret={false} icon="file" iconClass="" name="x" onActivate={onActivate}
      actions={[{ label: "Attach x", glyph: "@", run }]} /></div>);
    const btn = screen.getByRole("button", { name: "Attach x" });
    fireEvent.keyDown(btn, { key: "Enter" });
    fireEvent.click(btn);
    expect(run).toHaveBeenCalledTimes(1);
    expect(onActivate).not.toHaveBeenCalled();
  });

  it("sends on Enter and breaks the line on Shift+Enter", async () => {
    const sent = vi.fn().mockResolvedValue(undefined);
    const { container } = render(<Composer busy={false} onSend={sent} onStop={() => {}} attachments={[]}
      onAdd={() => {}} onRemove={() => {}} openDocs={[]} />);
    const box = container.querySelector("textarea")!;
    fireEvent.change(box, { target: { value: "hello" } });
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(sent).toHaveBeenCalledWith("hello", []));
    fireEvent.change(box, { target: { value: "line" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(sent).toHaveBeenCalledTimes(1);
  });
});
