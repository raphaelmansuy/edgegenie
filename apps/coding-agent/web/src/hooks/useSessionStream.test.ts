/** Regression: slow metadata must not erase streamed mission plans, outcome timing or failures. */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { useSessionStream } from "./useSessionStream";

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
