import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useTabDrag } from "./useTabDrag";

// Lifecycle failures leave captured pointers or animation frames behind. Exercise cancellation
// independently of the browser gesture journeys so cleanup remains covered after a refactor.
describe("tab drag lifecycle (TM-04/10)", () => {
  let el: HTMLDivElement;
  beforeEach(() => {
    vi.useFakeTimers();
    el = document.createElement("div");
    el.setPointerCapture = vi.fn(); el.hasPointerCapture = vi.fn(() => true); el.releasePointerCapture = vi.fn();
    el.getBoundingClientRect = () => ({ left: 0, right: 500, top: 0, bottom: 44, width: 500, height: 44, x: 0, y: 0, toJSON() {} });
    for (const [index, id] of ["a", "b"].entries()) {
      const tab = document.createElement("div"); tab.dataset.tabId = id;
      tab.getBoundingClientRect = () => ({ left: index * 150, right: (index + 1) * 150, top: 0, bottom: 44, width: 150, height: 44, x: index * 150, y: 0, toJSON() {} });
      el.append(tab);
    }
  });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });
  const event = (x = 20, extra: Record<string, unknown> = {}) => ({
    isPrimary: true, pointerId: 1, button: 0, pointerType: "mouse", clientX: x, clientY: 20,
    currentTarget: el, target: el.firstElementChild!, preventDefault: vi.fn(), ...extra,
  } as unknown as ReactPointerEvent<HTMLElement>);
  const setup = () => {
    const onMove = vi.fn();
    const hook = renderHook(({ ids }) => useTabDrag({ current: el }, ids, onMove), { initialProps: { ids: ["a", "b"] } });
    return { ...hook, onMove };
  };
  it("does not capture close controls, secondary pointers or the only tab", () => {
    const { result, rerender, onMove } = setup();
    const button = document.createElement("button");
    act(() => result.current.start(event(20, { target: button }), "a"));
    act(() => result.current.start(event(20, { isPrimary: false }), "a"));
    rerender({ ids: ["a"] }); act(() => result.current.start(event(), "a"));
    expect(el.setPointerCapture).not.toHaveBeenCalled(); expect(onMove).not.toHaveBeenCalled();
  });
  it("window blur cancels an active drag without committing and releases capture", () => {
    const { result, onMove } = setup();
    act(() => { result.current.start(event(), "a"); result.current.move(event(220)); });
    expect(result.current.drag).not.toBeNull();
    act(() => window.dispatchEvent(new Event("blur")));
    expect(result.current.drag).toBeNull(); expect(onMove).not.toHaveBeenCalled();
    expect(el.releasePointerCapture).toHaveBeenCalledWith(1);
  });
  it("source removal cancels; late release cannot move a different document", () => {
    const { result, rerender, onMove } = setup();
    act(() => { result.current.start(event(), "a"); result.current.move(event(220)); });
    rerender({ ids: ["b"] }); act(() => result.current.end(event(220)));
    expect(result.current.drag).toBeNull(); expect(onMove).not.toHaveBeenCalled();
  });
  it("unmount stops a pending touch hold and removes global listeners", () => {
    const { result, unmount, onMove } = setup();
    act(() => result.current.start(event(20, { pointerType: "touch" }), "a"));
    unmount(); act(() => vi.advanceTimersByTime(1000));
    expect(vi.getTimerCount()).toBe(0); expect(onMove).not.toHaveBeenCalled();
    expect(el.releasePointerCapture).toHaveBeenCalledWith(1);
  });
  it("unmount cancels the edge-autoscroll animation frame", () => {
    const { result, unmount } = setup();
    act(() => { result.current.start(event(), "a"); result.current.move(event(490)); });
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount(); expect(vi.getTimerCount()).toBe(0);
  });
});
