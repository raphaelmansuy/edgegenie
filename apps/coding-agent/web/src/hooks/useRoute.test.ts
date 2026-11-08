import { act, renderHook } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EMPTY_ROUTE, type Route } from "../domain/route";
import { useRoute } from "./useRoute";

const nb = (cell: number | null = null): Route => ({ ...EMPTY_ROUTE, doc: { kind: "notebook", ref: "/Users/a/b" }, cell });

describe("useRoute", () => {
  beforeEach(() => { window.history.replaceState(null, "", "/"); });

  it("applies the address on load, before it writes anything", () => {
    window.history.replaceState(null, "", "/#/notebook/Users/a/b?cell=2");
    const seen: Route[] = [];
    // The app: its state starts empty, and `apply` is what moves it (in the same batch as `ready`).
    renderHook(() => {
      const [r, setR] = useState<Route>(EMPTY_ROUTE);
      useRoute(r, (next) => { seen.push(next); setR(next); });
    });
    expect(seen[0]).toEqual(nb(2));
    // the app's empty first state must not have overwritten the link that was opened
    expect(window.location.hash).toBe("#/notebook/Users/a/b?cell=2");
  });

  it("pushes an entry for a move, and only replaces when the cell moves", () => {
    const apply = vi.fn();
    const { rerender } = renderHook(({ r }) => useRoute(r, apply), { initialProps: { r: EMPTY_ROUTE } });
    const start = window.history.length;
    rerender({ r: nb() });
    expect(window.location.hash).toBe("#/notebook/Users/a/b");
    expect(window.history.length).toBe(start + 1);
    rerender({ r: nb(3) });
    expect(window.location.hash).toBe("#/notebook/Users/a/b?cell=3");
    expect(window.history.length).toBe(start + 1);
  });

  it("clears the hash when the app returns to the start page", () => {
    const { rerender } = renderHook(({ r }) => useRoute(r, vi.fn()), { initialProps: { r: nb() } });
    rerender({ r: EMPTY_ROUTE });
    expect(window.location.hash).toBe("");
  });

  it("applies a hash change made from outside", () => {
    const apply = vi.fn();
    renderHook(() => useRoute(EMPTY_ROUTE, apply));
    apply.mockClear();
    act(() => {
      window.history.replaceState(null, "", "/#/settings/models");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(apply).toHaveBeenCalledWith({ ...EMPTY_ROUTE, settings: "models" });
  });
});
