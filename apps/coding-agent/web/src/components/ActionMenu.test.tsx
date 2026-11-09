import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionMenu } from "./ActionMenu";
afterEach(cleanup);
describe("shared action menu keyboard contract", () => {
  it("focuses first enabled action, navigates, activates once and returns focus", () => {
    const run = vi.fn();
    render(<ActionMenu label="Actions" actions={[{ label: "Disabled", disabled: true, onSelect: run }, { label: "Copy", onSelect: run }, null, { label: "Reload", onSelect: run }]}><span>More</span></ActionMenu>);
    const trigger = screen.getByRole("button", { name: "Actions" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" }); expect(screen.getByRole("menuitem", { name: "Copy" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "End" }); expect(screen.getByRole("menuitem", { name: "Reload" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" }); expect(screen.getByRole("menuitem", { name: "Copy" })).toHaveFocus();
    fireEvent.click(screen.getByRole("menuitem", { name: "Copy" })); expect(run).toHaveBeenCalledTimes(1); expect(trigger).toHaveFocus();
    expect(screen.queryByRole("menu")).toBeNull();
  });
  it("supports reverse entry, typeahead, Escape and outside dismissal", () => {
    render(<ActionMenu label="Actions" actions={[{ label: "Copy", onSelect() {} }, { label: "Reload", onSelect() {} }]}><span>More</span></ActionMenu>);
    const trigger = screen.getByRole("button", { name: "Actions" });
    fireEvent.keyDown(trigger, { key: "ArrowUp" }); expect(screen.getByRole("menuitem", { name: "Reload" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "c" }); expect(screen.getByRole("menuitem", { name: "Copy" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" }); expect(trigger).toHaveFocus();
    fireEvent.click(trigger); fireEvent.pointerDown(document.body); expect(screen.queryByRole("menu")).toBeNull();
  });
});
