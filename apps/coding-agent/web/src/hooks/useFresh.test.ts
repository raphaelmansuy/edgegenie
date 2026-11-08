import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { POLL_MS, SETTLE_MS, useFresh } from "./useFresh";
import { api } from "../api/client";

const flush = async (ms: number) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };

describe("useFresh", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it("does nothing while the agent is idle", async () => {
    const spy = vi.spyOn(api, "version").mockResolvedValue({ path: "/a", version: "v2", modifiedAt: 2 });
    const stale = vi.fn();
    renderHook(() => useFresh({ ref: "/a", known: "v1", live: false, stale }));
    await flush(POLL_MS * 3);
    expect(spy).not.toHaveBeenCalled();
    expect(stale).not.toHaveBeenCalled();
  });

  it("reloads once when the version moves while the agent works", async () => {
    vi.spyOn(api, "version").mockResolvedValue({ path: "/a", version: "v2", modifiedAt: 2 });
    const stale = vi.fn();
    renderHook(() => useFresh({ ref: "/a", known: "v1", live: true, stale }));
    await flush(POLL_MS * 3 + 10);
    expect(stale).toHaveBeenCalledTimes(1);          // three ticks saw v2, one reload
  });

  it("stays quiet while the version is the one it holds", async () => {
    vi.spyOn(api, "version").mockResolvedValue({ path: "/a", version: "v1", modifiedAt: 1 });
    const stale = vi.fn();
    renderHook(() => useFresh({ ref: "/a", known: "v1", live: true, stale }));
    await flush(POLL_MS * 2 + 10);
    expect(stale).not.toHaveBeenCalled();
  });

  it("checks once more after the turn ends", async () => {
    const spy = vi.spyOn(api, "version").mockResolvedValue({ path: "/a", version: "v2", modifiedAt: 2 });
    const stale = vi.fn();
    const { rerender } = renderHook(({ live }) => useFresh({ ref: "/a", known: "v1", live, stale }),
      { initialProps: { live: true } });
    rerender({ live: false });
    await flush(SETTLE_MS + 10);
    expect(spy).toHaveBeenCalled();
    expect(stale).toHaveBeenCalledTimes(1);
  });

  it("survives a failed check (the path is briefly absent during an overwrite)", async () => {
    const spy = vi.spyOn(api, "version").mockRejectedValueOnce(new Error("404")).mockResolvedValue({ path: "/a", version: "v2", modifiedAt: 2 });
    const stale = vi.fn();
    renderHook(() => useFresh({ ref: "/a", known: "v1", live: true, stale }));
    await flush(POLL_MS * 2 + 10);
    expect(spy).toHaveBeenCalledTimes(2);
    expect(stale).toHaveBeenCalledTimes(1);
  });

  it("does not ask before it has loaded anything", async () => {
    const spy = vi.spyOn(api, "version").mockResolvedValue({ path: "/a", version: "v2", modifiedAt: 2 });
    renderHook(() => useFresh({ ref: "/a", known: null, live: true, stale: vi.fn() }));
    await flush(POLL_MS * 2);
    expect(spy).not.toHaveBeenCalled();
  });
});
