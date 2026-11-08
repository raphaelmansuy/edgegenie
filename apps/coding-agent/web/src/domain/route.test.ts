import { describe, expect, it } from "vitest";
import { EMPTY_ROUTE, formatRoute, linkTo, parseRoute, sameRoute, type Route } from "./route";

const r = (over: Partial<Route>): Route => ({ ...EMPTY_ROUTE, ...over });

describe("formatRoute", () => {
  it("writes a notebook the way a person writes the path", () => {
    expect(formatRoute(r({ doc: { kind: "notebook", ref: "/Users/me@x.com/agent_scratch/etl" } })))
      .toBe("#/notebook/Users/me@x.com/agent_scratch/etl");
  });
  it("adds the cell only for a notebook", () => {
    expect(formatRoute(r({ doc: { kind: "notebook", ref: "/a/b" }, cell: 3 }))).toBe("#/notebook/a/b?cell=3");
    expect(formatRoute(r({ doc: { kind: "file", ref: "/a/b.py" }, cell: 3 }))).toBe("#/file/a/b.py");
  });
  it("encodes what would break a url", () => {
    expect(formatRoute(r({ doc: { kind: "notebook", ref: "/Users/me/my notebook #1?" } })))
      .toBe("#/notebook/Users/me/my%20notebook%20%231%3F");
  });
  it("writes sessions, settings, tables and the empty page", () => {
    expect(formatRoute(r({ session: "abc-123" }))).toBe("#/session/abc-123");
    expect(formatRoute(r({ settings: "models" }))).toBe("#/settings/models");
    expect(formatRoute(r({ doc: { kind: "table", ref: "main.sales.orders" } }))).toBe("#/table/main.sales.orders");
    expect(formatRoute(EMPTY_ROUTE)).toBe("");
  });
  it("settings win over what is underneath them", () => {
    expect(formatRoute(r({ settings: "providers", doc: { kind: "file", ref: "/x" } }))).toBe("#/settings/providers");
  });
});

describe("parseRoute", () => {
  const cases: Route[] = [
    r({ doc: { kind: "notebook", ref: "/Users/raphael.mansuy@gmail.com/agent_scratch/avg_fare_by_hour" } }),
    r({ doc: { kind: "notebook", ref: "/Shared/my notebook #1?" }, cell: 12 }),
    r({ doc: { kind: "file", ref: "/Users/me/lib/util.py" } }),
    r({ doc: { kind: "table", ref: "samples.nyctaxi.trips" } }),
    r({ session: "s_01HZX" }),
    r({ settings: "models" }),
    r({ settings: "providers" }),
    EMPTY_ROUTE,
  ];
  it.each(cases)("round-trips %j", (route) => expect(parseRoute(formatRoute(route))).toEqual(route));

  it("keeps the first release's settings links working", () => {
    expect(parseRoute("#settings/models")).toEqual(r({ settings: "models" }));
    expect(parseRoute("#settings/providers")).toEqual(r({ settings: "providers" }));
  });
  it("treats anything it does not know as the start page, never an error", () => {
    for (const bad of ["", "#", "#/", "#/nonsense/x", "#/notebook", "#/notebook/", "#/session", "#/table", "#%E0%A4%A"]) {
      expect(parseRoute(bad)).toEqual(EMPTY_ROUTE);
    }
  });
  it("ignores a cell that is not a positive whole number", () => {
    for (const q of ["0", "-1", "1.5", "x", ""]) expect(parseRoute(`#/notebook/a/b?cell=${q}`).cell).toBeNull();
    expect(parseRoute("#/notebook/a/b?cell=7").cell).toBe(7);
  });
  it("survives a bad percent escape inside a path", () => {
    expect(parseRoute("#/file/a/%E0%A4%A").doc?.ref).toBe("/a/%E0%A4%A");
  });
});

describe("helpers", () => {
  it("compares routes by their address", () => {
    expect(sameRoute(r({ session: "a" }), r({ session: "a" }))).toBe(true);
    expect(sameRoute(r({ session: "a" }), r({ session: "b" }))).toBe(false);
  });
  it("builds an absolute link on the current page", () => {
    expect(linkTo(r({ settings: "models" }), { origin: "https://app.example", pathname: "/" })).toBe("https://app.example/#/settings/models");
  });
});
