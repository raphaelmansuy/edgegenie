/** Regression: slow metadata must not erase streamed mission plans, outcome timing or failures. */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { useSessionStream } from "./useSessionStream";
import { emptySession } from "../domain/events";

class Source {
  static current: Source;
  static CLOSED = 2;
  readyState = 1;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  constructor() { Source.current = this; }
  close() { this.readyState = 2; }
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("keeps delivery pending through slow hydration and adopts POST acceptance without SSE", async () => {
  vi.stubGlobal("EventSource", Source);
  let detail!: (value: any) => void, accept!: (value: any) => void;
  vi.spyOn(api, "session").mockImplementation(() => new Promise(resolve => { detail = resolve; }));
  vi.spyOn(api, "send").mockImplementation(() => new Promise(resolve => { accept = resolve; }));
  const { result } = renderHook(() => useSessionStream("s"));
  let sent!: Promise<void>;
  act(() => { sent = result.current.send("Inspect sales"); });
  expect(result.current.session.turns[0].submission).toBe("sending");
  expect(result.current.session.status).not.toBe("streaming");
  await act(async () => detail({ ...emptySession("s"), status: "ready" }));
  expect(result.current.session.turns[0].prompt).toBe("Inspect sales");
  await act(async () => { accept({ turnId: "t", status: "queued" }); await sent; });
  expect(result.current.session.turns).toHaveLength(1);
  expect(result.current.session.turns[0]).toMatchObject({ id: "t", status: "queued", submission: undefined });
});

it("does not overwrite a completed streamed answer with a late POST acknowledgement", async () => {
  vi.stubGlobal("EventSource", Source);
  vi.spyOn(api, "session").mockResolvedValue({ ...emptySession("s"), status: "ready" } as any);
  let accept!: (value: any) => void;
  vi.spyOn(api, "send").mockImplementation(() => new Promise(resolve => { accept = resolve; }));
  const { result } = renderHook(() => useSessionStream("s"));
  await waitFor(() => expect(result.current.session.status).toBe("ready"));
  let sent!: Promise<void>;
  act(() => { sent = result.current.send("Inspect sales"); });
  act(() => {
    for (const [i, type, extra] of [[1, "turn.started", { text: "Inspect sales" }], [2, "message.delta", { text: "Done" }], [3, "turn.completed", {}]] as const)
      Source.current.onmessage?.({data: JSON.stringify({ seq: i, type, sessionId: "s", turnId: "t", ...extra })});
  });
  await waitFor(() => expect(result.current.session.turns[0].answer).toBe("Done"));
  await act(async () => { accept({ turnId: "t", status: "running" }); await sent; });
  expect(result.current.session.turns).toHaveLength(1);
  expect(result.current.session.turns[0]).toMatchObject({ answer: "Done", status: "completed" });
  expect(result.current.session.status).toBe("ready");
});

it("a refused follow-up preserves the running mission and a late failure cannot alter another session", async () => {
  vi.stubGlobal("EventSource", Source);
  vi.spyOn(api, "session").mockImplementation(async id => ({ ...emptySession(id), status: id === "s" ? "streaming" : "ready" } as any));
  let reject!: (e: Error) => void;
  vi.spyOn(api, "send").mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
  const { result, rerender } = renderHook(({ id }) => useSessionStream(id), { initialProps: { id: "s" } });
  await waitFor(() => expect(result.current.session.status).toBe("streaming"));
  let sent!: Promise<void>;
  act(() => { sent = result.current.send("Follow up").catch(() => {}); });
  await act(async () => { reject(new Error("Unavailable")); await sent; });
  expect(result.current.session.status).toBe("streaming");
  expect(result.current.session.turns).toHaveLength(0);
  act(() => { sent = result.current.send("Another").catch(() => {}); });
  rerender({ id: "other" });
  await waitFor(() => expect(result.current.session.id).toBe("other"));
  await act(async () => { reject(new Error("Old failure")); await sent; });
  expect(result.current.error).toBeNull();
  expect(result.current.session.status).toBe("ready");
});

it.each(["completed", "blocked"])("retains replayed mission details when metadata arrives after %s", async (status) => {
  vi.stubGlobal("EventSource", Source);
  let resolveDetail!: (value: Awaited<ReturnType<typeof api.session>>) => void;
  vi.spyOn(api, "session").mockImplementation(() => new Promise((resolve) => { resolveDetail = resolve; }));
  const { result } = renderHook(() => useSessionStream("s"));
  act(() => {
    Source.current.onopen?.();
    const emit = (seq: number, type: string, extra = {}) => Source.current.onmessage?.({ data: JSON.stringify({ seq, type, sessionId: "s", turnId: "t", ...extra }) });
    emit(1, "turn.started", { text: "Build report", model: "recorded/model" });
    emit(2, "plan.updated", { entries: [{ content: "Inspect schema", status: "completed" }] });
    emit(3, "message.delta", { text: "Saved result" });
    emit(4, "turn.auditing", { pass: 2 });
    emit(5, `turn.${status}`, { seconds: 7.5, reason: "Permission denied", missing: ["USE SCHEMA"] });
    emit(6, "sql.changed", { draftId: "draft", version: 3, runId: "run" });
  });
  await waitFor(() => expect(result.current.session.turns[0]?.plan).toHaveLength(1));
  await act(async () => resolveDetail({ id: "s", title: "Report", status: "ready", folder: "/Shared", model: "future/model",
    turns: [{ id: "t", index: 1, status, prompt: "Build report", model: "recorded/model" }] } as Awaited<ReturnType<typeof api.session>>));
  const turn = result.current.session.turns[0];
  expect(result.current.session.sqlChanges?.draft).toEqual({version:3,runId:"run",seq:6});
  expect(turn.plan).toEqual([{ content: "Inspect schema", status: "completed" }]);
  expect(turn.answer).toBe("Saved result"); expect(turn.auditPasses).toBe(2);
  if (status === "completed") expect(turn.seconds).toBe(7.5);
  else expect(turn.blocked).toMatchObject({ reason: "Permission denied", missing: ["USE SCHEMA"] });
});
