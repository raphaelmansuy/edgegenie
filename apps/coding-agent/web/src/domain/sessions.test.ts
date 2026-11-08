import { describe, expect, it } from "vitest";
import { bucketOf, groupSessions, initials, matches, sessionLabel } from "./sessions";

// 2026-11-08 13:00 local
const NOW = new Date(2026, 10, 8, 13, 0, 0).getTime() / 1000;
const at = (daysAgo: number, hour = 9) => new Date(2026, 10, 8 - daysAgo, hour, 0, 0).getTime() / 1000;
const s = (id: string, title: string, createdAt?: number, folder = "") => ({ id, title, createdAt, folder });

describe("bucketOf", () => {
  it("follows the reader's calendar days", () => {
    expect(bucketOf(at(0, 0), NOW)).toBe("Today");
    expect(bucketOf(at(1, 23), NOW)).toBe("Yesterday");
    expect(bucketOf(at(3), NOW)).toBe("Previous 7 days");
    expect(bucketOf(at(30), NOW)).toBe("Earlier");
  });
  it("treats a clock slightly ahead as today, and a missing date as earlier", () => {
    expect(bucketOf(NOW + 120, NOW)).toBe("Today");
    expect(bucketOf(undefined, NOW)).toBe("Earlier");
    expect(bucketOf(Number.NaN, NOW)).toBe("Earlier");
  });
});

describe("groupSessions", () => {
  const list = [s("a", "old", at(20)), s("b", "now", at(0, 12)), s("c", "yday", at(1)), s("d", "earlier today", at(0, 8))];
  it("orders days, newest first inside each, and omits empty days", () => {
    const g = groupSessions(list, "", NOW);
    expect(g.map((x) => x.label)).toEqual(["Today", "Yesterday", "Earlier"]);
    expect(g[0].items.map((x) => x.id)).toEqual(["b", "d"]);
  });
  it("filters by every word, across title and folder, case-insensitively", () => {
    const l = [s("a", "Revenue notebook", at(0), "/Users/me/taxi"), s("b", "Churn", at(0), "/Users/me/taxi")];
    expect(groupSessions(l, "REVENUE taxi", NOW)[0].items.map((x) => x.id)).toEqual(["a"]);
    expect(groupSessions(l, "nothing", NOW)).toEqual([]);
  });
  it("is total: no sessions, no groups", () => expect(groupSessions([], "x", NOW)).toEqual([]));
});

describe("labels", () => {
  it("shows a short id while the title is the default", () => {
    expect(sessionLabel(s("abcdef123456", "New session"))).toBe("abcdef12");
    expect(sessionLabel(s("abc", ""))).toBe("abc");
    expect(sessionLabel(s("abc", "Taxi"))).toBe("Taxi");
  });
  it("an empty query matches everything", () => expect(matches(s("a", "x"), "  ")).toBe(true));
});

describe("initials", () => {
  it.each([
    ["raphael.mansuy@gmail.com", "RM"], ["Ada Lovelace", "AL"], ["root", "RO"], ["x", "X"], ["", "?"], [null, "?"],
    ["jean-luc_picard@x.io", "JP"],
  ])("%s -> %s", (u, want) => expect(initials(u as string)).toBe(want));
});
