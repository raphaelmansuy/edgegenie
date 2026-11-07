import { describe, expect, it } from "vitest";
import { exactTime, relativeTime } from "./time";

const T = 1_760_000_000; // a fixed instant; every case is expressed relative to it

describe("relativeTime", () => {
  it("says nothing when there is no timestamp", () => {
    // The caller skips the element rather than rendering "Invalid Date" or a 1970 stamp.
    expect(relativeTime(undefined)).toBe("");
    expect(relativeTime(null)).toBe("");
    expect(relativeTime(0)).toBe("");
    expect(relativeTime(Number.NaN)).toBe("");
    expect(relativeTime(Number.POSITIVE_INFINITY)).toBe("");
  });

  it("reads as 'now' for anything in the last three quarters of a minute", () => {
    expect(relativeTime(T - 0, T)).toBe("now");
    expect(relativeTime(T - 44, T)).toBe("now");
  });

  it("treats a future timestamp as 'now', not a negative age", () => {
    // Clock skew between the browser and the server must not print "-1m".
    expect(relativeTime(T + 30, T)).toBe("now");
  });

  it("counts minutes, then hours, then days", () => {
    expect(relativeTime(T - 60, T)).toBe("1m");
    expect(relativeTime(T - 59 * 60, T)).toBe("59m");
    expect(relativeTime(T - 3 * 3600, T)).toBe("3h");
    expect(relativeTime(T - 23 * 3600, T)).toBe("23h");
    expect(relativeTime(T - 3 * 86400, T)).toBe("3d");
  });

  it("never says '0m' or '0h' once past the threshold", () => {
    // A rounding artefact that prints "0m" looks broken.
    for (const age of [45, 60, 90, 3599, 3600, 5400]) {
      expect(relativeTime(T - age, T)).not.toMatch(/^0[mdh]$/);
    }
  });

  it("switches to a weekday past a week, where a count stops helping", () => {
    const out = relativeTime(T - 9 * 86400, T);
    expect(out).toMatch(/^[A-Za-z]{2,}$/);
    expect(out).not.toMatch(/\d/);
  });
});

describe("exactTime", () => {
  it("gives a full date and time for the hover", () => {
    const out = exactTime(T);
    expect(out).toMatch(/\d{4}/);            // a year
    expect(out).toMatch(/\d{1,2}:\d{2}/);    // a clock time
  });

  it("says nothing for a missing timestamp", () => {
    expect(exactTime(undefined)).toBe("");
    expect(exactTime(0)).toBe("");
  });
});
