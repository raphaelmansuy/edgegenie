import { describe, expect, it } from "vitest";
import { ACTIONS, ACTIONS_FOR, docForNode, makeDoc, touched } from "./docs";
import { tokenize } from "./highlight";
import { reduce, emptySession, newTurn, PENDING } from "./events";

describe("highlight", () => {
  const samples: [string, string][] = [
    ["python", 'df = spark.table("a.b.c")  # load\nfor i in range(10):\n  print(f"{i}") """doc\nstring"""'],
    ["sql", "select count(*) from `main`.s.t where x = 'it''s' -- c\n/* block\n comment */ limit 10"],
    ["scala", "val x = 1 // c\n/* b */ def f() = null"],
    ["markdown", "# not code"],
    ["python", ""],
    ["python", "'unterminated"],
  ];
  it.each(samples)("never alters the text (%s)", (lang, text) => {
    expect(tokenize(text, lang).map((t) => t.text).join("")).toBe(text);
  });
  it("classifies the basics", () => {
    const t = tokenize('x = 1  # hi\nimport os', "python");
    const by = (c: string) => t.filter((x) => x.cls === c).map((x) => x.text);
    expect(by("comment")).toEqual(["# hi"]);
    expect(by("number")).toEqual(["1"]);
    expect(by("keyword")).toEqual(["import"]);
  });
  it("sql keywords are case-insensitive and strings keep escaped quotes", () => {
    const t = tokenize("SELECT 'it''s' FROM t", "sql");
    expect(t.filter((x) => x.cls === "keyword").map((x) => x.text)).toEqual(["SELECT", "FROM"]);
    expect(t.find((x) => x.cls === "string")?.text).toBe("'it''s'");
  });
  it("a hash inside a string is not a comment", () => {
    expect(tokenize('s = "a # b"', "python").some((x) => x.cls === "comment")).toBe(false);
  });
});

describe("touched: which object did a tool call change", () => {
  it("reads the path from a notebook write", () => {
    const r = touched("db_dbx_write_notebook", '{"path":"/Users/a@b.c/scratch/nb","cells":[...');
    expect(r?.doc.ref).toBe("/Users/a@b.c/scratch/nb");
    expect(r?.doc.kind).toBe("notebook");
    expect(r?.mutates).toBe(true);
  });
  it("a read is openable but does not mutate", () => {
    const r = touched("dbx_read_notebook", '{"path":"/Shared/x"}');
    expect(r).toMatchObject({ mutates: false });
  });
  it("never guesses: no path, relative path, or an unrelated tool", () => {
    expect(touched("dbx_write_notebook", "")).toBeNull();
    expect(touched("dbx_write_notebook", '{"path":"relative"}')).toBeNull();
    expect(touched("dbx_run_sql", '{"path":"/x"}')).toBeNull();
  });
});

describe("documents and actions", () => {
  it("folders are not documents", () => {
    expect(docForNode("directory", "/x")).toBeNull();
    expect(docForNode("repo", "/x")).toBeNull();
    expect(docForNode("notebook", "/x/nb")?.kind).toBe("notebook");
  });
  it("a table document is named by its table", () => {
    expect(makeDoc("table", "main.s.orders").name).toBe("orders");
  });
  it("every action that changes something promises to leave the original alone", () => {
    for (const a of ["fix", "document", "optimize"] as const) {
      expect(ACTIONS[a].prompt).toMatch(/working folder/);
      expect(ACTIONS[a].prompt).toMatch(/original|never modify/i);
    }
    expect(ACTIONS_FOR.table).toEqual(["profile", "query"]);
  });
});

describe("reducer: plan and attachments", () => {
  it("keeps the latest plan snapshot for the turn", () => {
    let s = reduce(emptySession("s"), { seq: 1, sessionId: "s", type: "turn.started", turnId: "t", text: "go", model: "m",
      attachments: [{ kind: "table", ref: "main.s.t", name: "main.s.t" }] });
    expect(s.turns[0].attachments?.[0].ref).toBe("main.s.t");
    s = reduce(s, { seq: 2, sessionId: "s", type: "plan.updated", turnId: "t", entries: [{ content: "a", status: "pending" }] });
    s = reduce(s, { seq: 3, sessionId: "s", type: "plan.updated", turnId: "t",
      entries: [{ content: "a", status: "completed" }, { content: "b", status: "in_progress" }] });
    expect(s.turns[0].plan?.map((p) => p.status)).toEqual(["completed", "in_progress"]);
  });
});

describe("optimistic turns", () => {
  it("the server's turn replaces the one shown at once, so the message appears once", () => {
    const s = { ...emptySession(), turns: [{ ...newTurn(`${PENDING}1`, 1, "hello"), status: "running" as const }] };
    const next = reduce(s, { type: "turn.started", turnId: "t1", text: "hello", sessionId: "x", seq: 1 } as never);
    expect(next.turns.map((t) => t.id)).toEqual(["t1"]);
    expect(next.turns[0].prompt).toBe("hello");
  });
});

import { append, MAX_ANSWER } from "./events";
describe("streamed text is bounded", () => {
  it("keeps growing under the limit", () => {
    expect(append("a", "b", 10)).toBe("ab");
  });
  it("keeps the newest text and says the start was dropped", () => {
    const big = append("a".repeat(50), "b", 10);
    expect(big).toBe("…" + "a".repeat(9) + "b");
    expect(append("x".repeat(MAX_ANSWER), "y", MAX_ANSWER).length).toBe(MAX_ANSWER + 1);
  });
});
