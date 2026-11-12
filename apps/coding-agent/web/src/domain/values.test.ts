import { describe, expect, it } from "vitest";
import { LONG_VALUE, formatNested, parseType, viewOf } from "./values";

describe("reading a Spark type", () => {
  it("reads arrays, maps, structs and what is inside them", () => {
    expect(parseType("ARRAY<INT>")).toEqual({ k: "array", of: { k: "leaf", name: "int" } });
    expect(parseType("MAP<STRING, INT>")).toEqual({ k: "map", key: { k: "leaf", name: "string" }, value: { k: "leaf", name: "int" } });
    expect(parseType("STRUCT<x: INT NOT NULL, y: STRING NOT NULL>")).toEqual({
      k: "struct", fields: [{ name: "x", type: { k: "leaf", name: "int" } }, { name: "y", type: { k: "leaf", name: "string" } }] });
  });
  it("reads Spark's own spelling, with no spaces and lower case", () => {
    expect(parseType("array<struct<p:int,q:array<string>>>")).toMatchObject({ k: "array", of: { k: "struct" } });
  });
  it("reads decimals, backticked names, and comments", () => {
    expect(parseType("ARRAY<DECIMAL(5,2)>")).toEqual({ k: "array", of: { k: "leaf", name: "decimal" } });
    expect(parseType("STRUCT<`a b`: INT COMMENT 'it''s', c: INT>")).toMatchObject({ fields: [{ name: "a b" }, { name: "c" }] });
  });
  it.each(["", undefined, "ARRAY<INT", "ARRAY<>", "STRUCT<x INT>", "MAP<STRING>", "ARRAY<INT> junk"])("gives up on %s", (t) => {
    expect(parseType(t)).toBeNull();
  });
  it("gives up on a type nested absurdly deep instead of overflowing", () => {
    expect(parseType("ARRAY<".repeat(40) + "INT" + ">".repeat(40))).toBeNull();
  });
});

describe("nested values are shown as values", () => {
  it("draws what the SQL API sends: every leaf a string", () => {
    expect(formatNested('["1","2"]', "ARRAY<INT>")).toBe("[1,2]");
    expect(formatNested('{"k":"1","j":"2"}', "MAP<STRING, INT>")).toBe('{"k":1,"j":2}');
    expect(formatNested('{"x":"1","y":"s"}', "STRUCT<x: INT NOT NULL, y: STRING NOT NULL>")).toBe('{"x":1,"y":"s"}');
    expect(formatNested('[{"p":"1"}]', "ARRAY<STRUCT<p: INT NOT NULL>>")).toBe('[{"p":1}]');
  });
  it("keeps a string a string, even one that looks like a number", () => {
    expect(formatNested('["1","a"]', "ARRAY<STRING>")).toBe('["1","a"]');
  });
  it("draws what Python sends: real numbers", () => {
    expect(formatNested("[1,2,null]", "array<int>")).toBe("[1,2,null]");
  });
  it("does not reformat numbers", () => {
    expect(formatNested('["1.50","9007199254740993"]', "ARRAY<DECIMAL(5,2)>")).toBe("[1.50,9007199254740993]");
    expect(formatNested('["1.50"]', "ARRAY<STRING>")).toBe('["1.50"]');
  });
  it("draws NULL leaves, booleans, and empty containers", () => {
    expect(formatNested('[null,"true"]', "ARRAY<BOOLEAN>")).toBe("[null,true]");
    expect(formatNested("[]", "ARRAY<INT>")).toBe("[]");
    expect(formatNested("{}", "MAP<STRING,INT>")).toBe("{}");
  });
  it("fills a missing struct field with null, in the type's order", () => {
    expect(formatNested('{"y":"s"}', "STRUCT<x:int,y:string>")).toBe('{"x":null,"y":"s"}');
  });
  it("breaks it over lines when asked", () => {
    expect(formatNested('{"x":"1","y":["a","b"]}', "STRUCT<x:int,y:array<string>>", true)).toBe(
      '{\n  "x": 1,\n  "y": [\n    "a",\n    "b"\n  ]\n}');
  });
  it("leaves a value alone when it cannot read it", () => {
    expect(formatNested("not json", "ARRAY<INT>")).toBeNull();
    expect(formatNested('["1"]', undefined)).toBeNull();
    expect(formatNested('["1"]', "STRING")).toBeNull();
    expect(formatNested("{[", "ARRAY<INT>")).toBeNull();
  });
  it("shows the raw JSON when the value's shape is not the type's", () => {
    expect(formatNested('{"a":1}', "ARRAY<INT>")).toBe('{"a":1}');
  });
});

describe("a cell view", () => {
  it("shows a plain value as it is", () => {
    expect(viewOf("hello", "STRING")).toMatchObject({ text: "hello", nested: false, long: false, full: "hello" });
  });
  it("shows a nested one typed, with a pretty expansion", () => {
    const v = viewOf('["1","2"]', "ARRAY<INT>");
    expect(v).toMatchObject({ text: "[1,2]", nested: true, long: false });
    expect(v.full).toBe("[\n  1,\n  2\n]");
  });
  it("shortens a long value and keeps all of it for Expand and Copy", () => {
    const raw = "x".repeat(LONG_VALUE + 50);
    const v = viewOf(raw);
    expect(v.long).toBe(true);
    expect(v.short).toBe(`${"x".repeat(LONG_VALUE)}…`);
    expect(v.copy).toBe(raw);
    expect(v.full).toBe(raw);
  });
  it("measures a nested value after formatting, not before", () => {
    const raw = JSON.stringify(Array.from({ length: 40 }, () => "1"));
    expect(raw.length).toBeGreaterThan(LONG_VALUE);
    expect(viewOf(raw, "ARRAY<INT>").long).toBe(false);
  });
});
