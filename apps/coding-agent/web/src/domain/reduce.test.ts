import { describe, expect, it } from "vitest";
import { emptySession, newTurn, reduce, EVENT_TYPES, type AgentEvent, type SessionView } from "./events";

const ev = (e: Partial<AgentEvent> & { type: string }): AgentEvent =>
  ({ seq: 1, sessionId: "s", ...e }) as AgentEvent;

describe("reducer", () => {
  it("adds a turn and streams its answer", () => {
    let s = emptySession("s");
    s = reduce(s, ev({ type: "turn.started", turnId: "t1", text: "Build it", model: "m/a" }));
    s = reduce(s, ev({ type: "message.delta", turnId: "t1", text: "Hello " }));
    s = reduce(s, ev({ type: "message.delta", turnId: "t1", text: "world" }));
    expect(s.turns).toHaveLength(1);
    expect(s.turns[0].answer).toBe("Hello world");
    expect(s.turns[0].prompt).toBe("Build it");
  });

  it("replaying turn.started onto a turn the detail route already inserted keeps one turn", () => {
    // Measured on the live app: one "Hello" produced one server turn and two message deltas,
    // and the dock drew two conversations because hydration and the stream each inserted the turn.
    let s: SessionView = { ...emptySession("s"), turns: [{ ...newTurn("t1", 1, "Hello", "m"), status: "completed" }] };
    s = reduce(s, ev({ type: "turn.started", turnId: "t1", text: "Hello", model: "m" }));
    s = reduce(s, ev({ seq: 2, type: "message.delta", turnId: "t1", text: "Hello! " }));
    s = reduce(s, ev({ seq: 3, type: "message.delta", turnId: "t1", text: "How can I help?" }));
    expect(s.turns).toHaveLength(1);
    expect(s.turns[0].prompt).toBe("Hello");
    expect(s.turns[0].answer).toBe("Hello! How can I help?");
  });

  it("keeps tool cards in order and updates in place", () => {
    let s = emptySession("s");
    s = reduce(s, ev({ type: "turn.started", turnId: "t1" }));
    s = reduce(s, ev({ type: "tool_call.started", turnId: "t1", callId: "a", name: "dbx_run_sql" }));
    s = reduce(s, ev({ type: "tool_call.started", turnId: "t1", callId: "b", name: "dbx_write_notebook" }));
    s = reduce(s, ev({ type: "tool_call.updated", turnId: "t1", callId: "a", status: "completed", seconds: 1.2 }));
    expect(s.turns[0].tools.map((t) => t.callId)).toEqual(["a", "b"]);
    expect(s.turns[0].tools[0].status).toBe("completed");
    expect(s.turns[0].tools[0].seconds).toBe(1.2);
  });

  it("a repeated tool_call.started does not duplicate the card", () => {
    let s = emptySession("s");
    s = reduce(s, ev({ type: "turn.started", turnId: "t1" }));
    s = reduce(s, ev({ type: "tool_call.started", turnId: "t1", callId: "a", name: "x" }));
    s = reduce(s, ev({ type: "tool_call.started", turnId: "t1", callId: "a", name: "x" }));
    expect(s.turns[0].tools).toHaveLength(1);
  });

  it("is idempotent for a replayed event", () => {
    let s = emptySession("s");
    s = reduce(s, ev({ type: "turn.started", turnId: "t1" }));
    const once = reduce(s, ev({ type: "message.delta", turnId: "t1", text: "x" }));
    const twice = reduce(once, ev({ type: "message.delta", turnId: "t1", text: "x" }));
    expect(twice.turns[0].answer).toBe("xx"); // the stream layer drops repeats by seq
  });

  it("ignores unknown events instead of crashing", () => {
    const s = reduce(emptySession("s"), ev({ type: "something.from.the.future" }));
    expect(s.turns).toHaveLength(0);
  });

  it("records evidence and a blocked reason", () => {
    let s = emptySession("s");
    s = reduce(s, ev({ type: "turn.started", turnId: "t1" }));
    s = reduce(s, ev({ type: "evidence.proposed", turnId: "t1",
      rows: [{ requirement: "a", toolCallId: "c", tool: "dbx_run_sql", summary: "", verified: true }] }));
    s = reduce(s, ev({ type: "turn.blocked", turnId: "t1", reason: "missing", missing: ["b"], attempted: [] }));
    expect(s.turns[0].evidence[0].verified).toBe(true);
    expect(s.turns[0].status).toBe("blocked");
    expect(s.turns[0].blocked?.missing).toEqual(["b"]);
  });

  it("marks the session ready when a turn completes", () => {
    let s = emptySession("s");
    s = reduce(s, ev({ type: "session.ready", toolCount: 19, agent: "FakeAgent" }));
    s = reduce(s, ev({ type: "turn.started", turnId: "t1" }));
    s = reduce(s, ev({ type: "turn.completed", turnId: "t1", usage: { inputTokens: 5, outputTokens: 2 } }));
    expect(s.status).toBe("ready");
    expect(s.tools).toBe(19);
    expect(s.turns[0].status).toBe("completed");
  });

  it("tracks approvals until they are decided", () => {
    let s = emptySession("s");
    s = reduce(s, ev({ type: "approval.requested", approvalId: "ap1", target: "workspace.default.t",
      action: "write", reason: "needs a shared table", options: [{ optionId: "o1", kind: "allow_once", name: "Allow" }] }));
    expect(s.approvals).toHaveLength(1);
    s = reduce(s, ev({ type: "approval.decided", approvalId: "ap1", outcome: "deny" }));
    expect(s.approvals[0].outcome).toBe("deny");
  });

  it("keeps every event type the server can send", async () => {
    const py = await import("./event-parity.json");
    expect(new Set(py.default.types)).toEqual(new Set(EVENT_TYPES));
  });
});

it("keeps protocol usage and explicit refusal outcomes", () => {
  let s = reduce(emptySession("s"), { seq: 1, sessionId: "s", type: "turn.started", turnId: "t", text: "test" });
  s = reduce(s, { seq: 2, sessionId: "s", type: "usage.updated", usage: { used: 12, size: 100, cost: { amount: .01, currency: "USD" } } });
  expect(s.meter?.used).toBe(12);
  s = reduce(s, { seq: 3, sessionId: "s", type: "turn.declined", turnId: "t", reason: "Stopped by your decision" });
  expect(s.turns[0].status).toBe("declined");
});

it("refreshes assets only from applied ledger state and retains the latest transition", () => {
  let s = emptySession("s");
  s = reduce(s, ev({ type: "change.proposed", change: { id: "c", state: "awaiting_review", asset: { kind: "notebook", id: "/scratch/n" } } }));
  expect(s.changedAssets).toBeUndefined();
  s = reduce(s, ev({ type: "change.applied", change: { id: "c", version: 2, state: "applied", asset: { kind: "notebook", id: "/scratch/n" } } }));
  expect(s.changedAssets).toEqual([{ kind: "notebook", id: "/scratch/n", key: "c:2:applied" }]);
  s = reduce(s, ev({ type: "change.settled", change: { id: "c", version: 3, state: "reverted", asset: { kind: "notebook", id: "/scratch/n" } } }));
  expect(s.changedAssets).toEqual([{ kind: "notebook", id: "/scratch/n", key: "c:3:reverted" }]);
});

it.each([true,false])('a linked native proposal remains a pending owner decision, link-first=%s',linkFirst=>{
 let s=emptySession('s');
 const linked=ev({type:'approval.linked',approvalId:'a',changeId:'c'}),requested=ev({type:'approval.requested',approvalId:'a',callId:'call',action:'edit'});
 for(const event of linkFirst?[linked,requested]:[requested,linked])s=reduce(s,event);
 expect(s.approvals[0].changeId).toBe('c');expect(s.approvals[0].outcome).toBeUndefined();
 s=reduce(s,ev({type:'approval.decided',approvalId:'a',outcome:'allow_once'}));
 expect(s.approvals[0].outcome).toBe('allow_once');
});
