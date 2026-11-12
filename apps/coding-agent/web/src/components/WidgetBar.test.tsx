import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BarItem } from "../domain/widgets";
import { WidgetBar } from "./WidgetBar";

const item = (over: Partial<BarItem> & { name: string }): BarItem =>
  ({ label: over.name, kind: "text", choices: [], default: "", implicit: false, ...over });

describe("the widget bar", () => {
  const draw = (items: BarItem[], values: Record<string, string> = {}, onChange = vi.fn(), onReset = vi.fn()) => {
    render(<WidgetBar items={items} values={values} onChange={onChange} onReset={onReset} />);
    return { onChange, onReset };
  };

  it("draws nothing when there is nothing to ask", () => {
    const { container } = render(<WidgetBar items={[]} values={{}} onChange={vi.fn()} onReset={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says that changing a widget does not run anything", () => {
    draw([item({ name: "city" })]);
    expect(screen.getByText(/does not re-run any cell/)).toBeInTheDocument();
  });

  it("draws a text input with its default, and reports what is typed", () => {
    const { onChange } = draw([item({ name: "city", label: "City", default: "Oslo" })]);
    const box = screen.getByLabelText("City") as HTMLInputElement;
    expect(box.value).toBe("Oslo");
    fireEvent.change(box, { target: { value: "Rome" } });
    expect(onChange).toHaveBeenCalledWith("city", "Rome");
  });

  it("shows the person's value over the default", () => {
    draw([item({ name: "city", default: "Oslo" })], { city: "Rome" });
    expect((screen.getByLabelText("city") as HTMLInputElement).value).toBe("Rome");
  });

  it("draws a dropdown of its choices, and a value it does not allow is shown as the default", () => {
    draw([item({ name: "size", kind: "dropdown", choices: ["s", "m"], default: "m" })], { size: "xl" });
    const select = screen.getByLabelText("size") as HTMLSelectElement;
    expect(select.value).toBe("m");
    expect([...select.options].map((o) => o.value)).toEqual(["s", "m"]);
  });

  it("draws a multiselect as checkboxes and keeps the widget's order", () => {
    const { onChange } = draw([item({ name: "pick", kind: "multiselect", choices: ["x", "y", "z"], default: "x" })], { pick: "z" });
    expect(screen.getByRole("checkbox", { name: "z" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "x" })).not.toBeChecked();
    fireEvent.click(screen.getByRole("checkbox", { name: "x" }));
    expect(onChange).toHaveBeenCalledWith("pick", "x,z");
  });

  it("draws a combobox as a text box with suggestions", () => {
    const { container } = render(<WidgetBar items={[item({ name: "tag", kind: "combobox", choices: ["a", "b"], default: "a" })]}
      values={{}} onChange={vi.fn()} onReset={vi.fn()} />);
    expect(container.querySelectorAll("datalist option")).toHaveLength(2);
  });

  it("marks a text box that only a SQL cell asked for", () => {
    draw([item({ name: "min", implicit: true })]);
    expect(screen.getByText("· SQL")).toBeInTheDocument();
  });

  it("offers Reset only when something differs from its default", () => {
    const { onReset } = draw([item({ name: "city", default: "Oslo" })], { city: "Rome" });
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(onReset).toHaveBeenCalled();
  });

  it("has Reset off when every widget has its default", () => {
    draw([item({ name: "city", default: "Oslo" })], { city: "Oslo" });
    expect(screen.getByRole("button", { name: "Reset" })).toBeDisabled();
  });
});
