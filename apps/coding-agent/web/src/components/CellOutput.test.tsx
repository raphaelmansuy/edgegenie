import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CellRun } from "../domain/cellrun";
import { CellOutput } from "./CellOutput";

const draw = (run: CellRun, extra: Partial<Parameters<typeof CellOutput>[0]> = {}) =>
  render(<CellOutput run={run} onClear={vi.fn()} {...extra} />);

describe("a cell's output", () => {
  it("draws what a Python cell produced in the order it produced it", () => {
    const { container } = draw({ state: "succeeded", seconds: 1, outputs: [
      { type: "text", stream: "stdout", text: "first\n" },
      { type: "table", columns: ["a"], rows: [["1"]], types: ["int"] },
      { type: "text", stream: "stdout", text: "second\n" },
      { type: "table", columns: ["b"], rows: [["x"]], types: ["string"] },
    ] });
    const kids = [...container.querySelector(".cell-output")!.children]
      .filter((el) => !el.classList.contains("cell-output-bar"))
      .map((el) => (el.tagName === "PRE" ? el.textContent!.trim() : "table"));
    expect(kids).toEqual(["first", "table", "second", "table"]);
    expect(screen.getByLabelText("Result 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Result 2")).toBeInTheDocument();
  });

  it("gives every table its own filter, so two results do not share a search box", () => {
    draw({ state: "succeeded", seconds: 1, outputs: [
      { type: "table", columns: ["a"], rows: [["apple"], ["pear"]] },
      { type: "table", columns: ["b"], rows: [["apple"], ["plum"]] },
    ] });
    const boxes = screen.getAllByLabelText("Filter rows");
    fireEvent.change(boxes[0], { target: { value: "pear" } });
    expect(within(screen.getByLabelText("Result 1")).getByText("pear")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Result 1")).queryByText("apple")).toBeNull();
    expect(within(screen.getByLabelText("Result 2")).getByText("apple")).toBeInTheDocument();
  });

  it("shows stderr apart from stdout, and a notice as a notice", () => {
    draw({ state: "succeeded", seconds: 1, outputs: [
      { type: "text", stream: "stdout", text: "ok" }, { type: "text", stream: "stderr", text: "warn" },
      { type: "text", stream: "notice", text: "2 outputs not shown" },
    ] });
    expect(screen.getByLabelText("Printed output")).toHaveClass("is-stdout");
    expect(screen.getByLabelText("Error stream")).toHaveClass("is-stderr");
    expect(screen.getByLabelText("Notice")).toHaveClass("is-notice");
  });

  it("right-aligns number columns by type and not a text column of digits", () => {
    draw({ state: "succeeded", seconds: 1, columns: ["id", "zip"], types: ["int", "string"],
      rows: [["1", "94105"], ["2", "10001"]] });
    const [idHead, zipHead] = screen.getAllByRole("columnheader");
    expect(idHead).toHaveClass("is-num");
    expect(zipHead).not.toHaveClass("is-num");
    expect(screen.getByText("94105").closest("td")).not.toHaveClass("is-num");
    expect(screen.getAllByRole("cell")[2]).toHaveClass("is-num");
    expect(idHead).toHaveAttribute("title", "id · int");
  });

  it("tells a NULL from an empty string", () => {
    const { container } = draw({ state: "succeeded", seconds: 1, columns: ["a", "b"], rows: [[null, ""]] });
    const cells = container.querySelectorAll("tbody td");
    expect(cells[0].querySelector("em.cell-null")?.textContent).toBe("null");
    expect(cells[1].querySelector("em")).toBeNull();
  });

  it("does not collapse columns that have the same name", () => {
    draw({ state: "succeeded", seconds: 1, columns: ["id", "id"], rows: [["1", "2"]] });
    expect(screen.getAllByRole("columnheader")).toHaveLength(2);
  });

  it("says when a table was cut", () => {
    draw({ state: "succeeded", seconds: 1, columns: ["a"], rows: [["1"]], truncated: true, totalRows: 5000 });
    expect(screen.getByText("Showing the first 1 of 5,000 rows")).toBeInTheDocument();
  });

  it("says OK for a statement that returned no result set", () => {
    draw({ state: "succeeded", seconds: 0.4, output: "OK" });
    expect(screen.getByLabelText("Printed output")).toHaveTextContent("OK");
  });

  it("puts the error under what the cell printed before it failed", () => {
    const { container } = draw({ state: "failed", seconds: 1, error: "Traceback...\nNameError: x",
      outputs: [{ type: "text", stream: "stdout", text: "before\n" }] });
    const body = [...container.querySelector(".cell-output")!.children].map((el) => el.className);
    expect(body.findIndex((c) => c.includes("cell-output-text")))
      .toBeLessThan(body.findIndex((c) => c.includes("cell-output-msg")));
    expect(screen.getByRole("alert")).toHaveTextContent("NameError: x");
  });

  it("names who ran it and when, beside the duration", () => {
    draw({ state: "succeeded", seconds: 1.2, ranBy: "a@x.com", finishedAt: "2020-01-02T03:04:05+00:00" });
    expect(screen.getByText(/by a@x\.com on .* at /)).toBeInTheDocument();
  });

  it("draws HTML in a sandboxed frame that cannot reach the app", () => {
    draw({ state: "succeeded", seconds: 1, outputs: [{ type: "html", html: "<b>hi</b>" }] });
    const frame = screen.getByTitle("HTML output") as HTMLIFrameElement;
    expect(frame.getAttribute("sandbox")).toContain("allow-scripts");
    expect(frame.getAttribute("sandbox")).not.toContain("allow-same-origin");
    expect(frame.getAttribute("srcdoc")).toContain("<b>hi</b>");
  });

  it("draws markdown as markdown, in the page, not as text", () => {
    draw({ state: "succeeded", seconds: 1, outputs: [{ type: "markdown", text: "## A title\n\n- one\n- two" }] });
    expect(screen.getByRole("heading", { name: "A title" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  describe("nested and long values", () => {
    const table = (rows: (string | null)[][], types: string[], typeTexts?: string[]) =>
      draw({ state: "succeeded", seconds: 1, outputs: [{ type: "table", columns: ["v"], rows, types, typeTexts }] });

    it("shows an array as an array of numbers, with the type as its tooltip", () => {
      table([['["1","2"]']], ["array"], ["ARRAY<INT>"]);
      const cell = screen.getByText("[1,2]");
      expect(cell.closest("[title]")?.getAttribute("title")).toBe("ARRAY<INT>");
    });

    it("leaves a nested value as it came when it has no type text", () => {
      table([['["1","2"]']], ["array"]);
      expect(screen.getByText('["1","2"]')).toBeInTheDocument();
    });

    it("shortens a long value, expands it, and copies the whole of it", async () => {
      const long = "word ".repeat(60).trim();
      const write = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText: write } });
      table([[long]], ["string"]);
      expect(screen.queryByText(long)).toBeNull();
      const expand = screen.getByRole("button", { name: "Expand" });
      expect(expand).toHaveAttribute("aria-expanded", "false");
      fireEvent.click(expand);
      expect(screen.getByRole("button", { name: "Collapse" })).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText(long)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Copy this value" }));
      await waitFor(() => expect(write).toHaveBeenCalledWith(long));
    });

    it("copies the visible rows with nested values as they are shown", async () => {
      const write = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText: write } });
      table([['["1","2"]']], ["array"], ["ARRAY<INT>"]);
      fireEvent.click(screen.getByRole("button", { name: "Copy the visible rows" }));
      await waitFor(() => expect(write).toHaveBeenCalledWith("v\n[1,2]"));
    });
  });

  describe("table or chart", () => {
    const trips = (views?: CellRun["views"]): CellRun => ({
      state: "succeeded", seconds: 1, views,
      outputs: [{ type: "table", columns: ["period", "trips"], types: ["string", "int"], rows: [["am", "40"], ["pm", "10"]] }],
    });

    it("offers a chart switch and tells the parent what was chosen", () => {
      const onView = vi.fn();
      draw(trips(), { onView });
      expect(screen.getByRole("button", { name: "Table" })).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(screen.getByRole("button", { name: "Chart" }));
      expect(onView).toHaveBeenCalledWith(0, { mode: "chart", spec: { kind: "bar", x: 0, y: 1, group: null } });
    });

    it("draws the chart that was stored with the result, with its legend and a sentence for a screen reader", () => {
      draw(trips({ "0": { mode: "chart", spec: { kind: "pie", x: 0, y: 1, group: null } } }), { onView: vi.fn() });
      expect(screen.getByRole("img", { name: "Pie chart of trips by period: 2 points." })).toBeInTheDocument();
      expect(within(screen.getByRole("list", { name: "Slices" })).getByText(/40 · 80\.0%/)).toBeInTheDocument();
      expect(screen.queryByRole("table")).toBeNull();
    });

    it("changing the chart type is passed on, keeping the other choices", () => {
      const onView = vi.fn();
      draw(trips({ "0": { mode: "chart", spec: { kind: "bar", x: 0, y: 1, group: null } } }), { onView });
      fireEvent.change(screen.getByLabelText("Type"), { target: { value: "line" } });
      expect(onView).toHaveBeenCalledWith(0, { mode: "chart", spec: { kind: "line", x: 0, y: 1, group: null } });
    });

    it("explains why a table of text cannot be charted", () => {
      draw({ state: "succeeded", seconds: 1, outputs: [{ type: "table", columns: ["a", "b"], types: ["string", "string"], rows: [["x", "y"]] }] }, { onView: vi.fn() });
      const chart = screen.getByRole("button", { name: "Chart" });
      expect(chart).toBeDisabled();
      expect(chart).toHaveAttribute("title", "A chart needs a column of numbers");
    });

    it("falls back to the table when the stored chart does not fit this result", () => {
      draw(trips({ "0": { mode: "chart", spec: { kind: "bar", x: 0, y: 0, group: null } } }), { onView: vi.fn() });
      expect(screen.getByRole("img", { name: /Bar chart of trips by period/ })).toBeInTheDocument();   // replaced by the default
    });

    it("does not offer the switch while the cell is running or when nobody listens", () => {
      draw(trips());
      expect(screen.queryByRole("button", { name: "Chart" })).toBeNull();
    });
  });

  it("numbers plots only when there are several", () => {
    draw({ state: "succeeded", seconds: 1, outputs: [{ type: "image", png: "a" }, { type: "image", png: "b" }] });
    expect(screen.getByAltText("Plot 1")).toBeInTheDocument();
    expect(screen.getByAltText("Plot 2")).toBeInTheDocument();
  });

  it("shows a running cell's note and no output yet", () => {
    draw({ state: "running", seconds: 3, error: "running on Shared… 3s", output: "partial" });
    expect(screen.getByRole("status")).toHaveTextContent("running on Shared… 3s");
    expect(screen.queryByLabelText("Printed output")).toBeNull();
  });
});
