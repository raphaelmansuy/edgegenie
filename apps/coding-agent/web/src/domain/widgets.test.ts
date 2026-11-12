import { describe, expect, it } from "vitest";
import {
  KEY, NO_WIDGETS, applyReport, barItems, load, paramsFor, resetValues, save, setValue, sqlParams, toggleChoice, valueOf,
  valuesForSession, type BarItem, type Widget,
} from "./widgets";

const w = (over: Partial<Widget> & { name: string }): Widget => ({ type: "text", default: "", label: over.name, choices: [], ...over });

describe("SQL parameters (the same cases the server's sql_params is tested with)", () => {
  it.each([
    ["select :a, :b, :a", ["a", "b"]],
    ["select a::int, raw:field from t", []],
    ["select ':no', \":no\", `:no`, 'it''s :no', :yes", ["yes"]],
    ["-- :no\nselect :yes /* :no */, :yes2", ["yes", "yes2"]],
    ["select 'a\\' :no', :ok", ["ok"]],
    ["where d = :start_date and e = :_x1", ["start_date", "_x1"]],
    ["select 1:2, :1", []],
    ["select :", []],
    ["select 'open :no", []],
  ])("%s", (sql, names) => {
    expect(sqlParams(sql)).toEqual(names);
  });
});

describe("the bar", () => {
  const sql = { kind: "code", language: "sql", source: "select * from t where city = :city and n > :min" };
  it("shows declared widgets, then a text box for each SQL marker nothing declares", () => {
    const items = barItems([w({ name: "city", default: "Oslo", label: "City" })], [sql]);
    expect(items.map((i) => [i.name, i.label, i.implicit])).toEqual([["city", "City", false], ["min", "min", true]]);
  });
  it("reads a %sql cell in a Python notebook, and ignores markdown and Python", () => {
    const items = barItems([], [
      { kind: "code", language: "python", source: "%sql\nselect :a" }, { kind: "markdown", language: "markdown", source: "select :b" },
      { kind: "code", language: "python", source: "x = {'k': :c}" }]);
    expect(items.map((i) => i.name)).toEqual(["a"]);
  });
  it("shows nothing when there is nothing to ask", () => {
    expect(barItems([], [{ kind: "code", language: "python", source: "x = 1" }])).toEqual([]);
  });
});

describe("a widget's value", () => {
  const dropdown: BarItem = { name: "size", label: "size", kind: "dropdown", choices: ["s", "m"], default: "m", implicit: false };
  const multi: BarItem = { ...dropdown, name: "pick", kind: "multiselect", choices: ["x", "y", "z"], default: "x" };
  const combo: BarItem = { ...dropdown, name: "tag", kind: "combobox", choices: ["a"], default: "a" };
  it("is the default until the person sets one", () => {
    expect(valueOf(dropdown, {})).toBe("m");
    expect(valueOf(dropdown, { size: "s" })).toBe("s");
  });
  it("falls back to the default for a value the widget does not allow, as the session does", () => {
    expect(valueOf(dropdown, { size: "xl" })).toBe("m");
    expect(valueOf(multi, { pick: "x,nope" })).toBe("x");
    expect(valueOf(multi, { pick: "x,z" })).toBe("x,z");
    expect(valueOf(combo, { tag: "anything" })).toBe("anything");
  });
  it("keeps a multiselect in the widget's own order", () => {
    expect(toggleChoice(multi, "z", "x")).toBe("x,z");
    expect(toggleChoice(multi, "x,z", "z")).toBe("x");
    expect(toggleChoice(multi, "", "y")).toBe("y");
  });
  it("is limited in length", () => {
    expect(valueOf({ ...combo, kind: "text" }, { tag: "x".repeat(5000) })).toHaveLength(2000);
    expect(setValue(NO_WIDGETS, "a", "x".repeat(5000)).values.a).toHaveLength(2000);
  });
});

describe("what a run is sent", () => {
  const items = barItems([w({ name: "city", default: "Oslo" })], []);
  it("sends a SQL cell only the markers it uses that have a widget", () => {
    expect(paramsFor("select :city, :other", items, { city: "Rome", unused: "x" })).toEqual({ city: "Rome" });
    expect(paramsFor("select 1", items, { city: "Rome" })).toEqual({});
  });
  it("sends the default for a widget the person has not touched", () => {
    expect(paramsFor("select :city", items, {})).toEqual({ city: "Oslo" });
  });
  it("sends a Python cell every declared widget's value", () => {
    expect(valuesForSession([w({ name: "a", default: "1" }), w({ name: "b", default: "2" })], { b: "9" })).toEqual({ a: "1", b: "9" });
  });
});

describe("state", () => {
  it("takes the declared set a session reports, including an empty one, and ignores a run that did not report", () => {
    const s = { declared: [w({ name: "a" })], values: { a: "1" } };
    expect(applyReport(s, [w({ name: "b" })]).declared.map((x) => x.name)).toEqual(["b"]);
    expect(applyReport(s, []).declared).toEqual([]);
    expect(applyReport(s, undefined)).toBe(s);
    expect(applyReport(s, []).values).toEqual({ a: "1" });       // what the person typed is kept for when it returns
  });
  it("resets to the defaults", () => {
    expect(resetValues({ declared: [w({ name: "a" })], values: { a: "1" } }).values).toEqual({});
  });
});

describe("keeping widgets per notebook", () => {
  const store = () => {
    const m = new Map<string, string>();
    return { m, getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) };
  };
  it("round-trips, per path", () => {
    const s = store();
    const state = { declared: [w({ name: "a", default: "1" })], values: { a: "2" } };
    save("/a", state, s);
    expect(load("/a", s)).toEqual(state);
    expect(load("/b", s)).toEqual(NO_WIDGETS);
  });
  it("forgets a notebook that has nothing", () => {
    const s = store();
    save("/a", { declared: [w({ name: "a" })], values: {} }, s);
    save("/a", NO_WIDGETS, s);
    expect(s.m.has(KEY + "/a")).toBe(false);
  });
  it("survives junk, and drops a declaration that is not one", () => {
    const s = store();
    s.m.set(KEY + "/a", "not json");
    expect(load("/a", s)).toEqual(NO_WIDGETS);
    s.m.set(KEY + "/a", JSON.stringify({ declared: [{ name: "x" }, w({ name: "ok" }), 5], values: { a: 1, b: "2" } }));
    const got = load("/a", s);
    expect(got.declared.map((d) => d.name)).toEqual(["ok"]);
    expect(got.values).toEqual({ b: "2" });
  });
  it("does not throw when storage refuses", () => {
    expect(() => save("/a", { declared: [w({ name: "a" })], values: {} }, { setItem: () => { throw new Error("full"); }, removeItem: () => {} })).not.toThrow();
  });
});
