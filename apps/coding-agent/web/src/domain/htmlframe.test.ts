import { describe, expect, it } from "vitest";
import { FRAME_SANDBOX, MAX_FRAME, MIN_FRAME, frameDoc, frameHeight } from "./htmlframe";

describe("the sandbox for HTML a notebook produced", () => {
  it("lets scripts run and never lets the page reach the app", () => {
    expect(FRAME_SANDBOX.split(" ")).toContain("allow-scripts");
    expect(FRAME_SANDBOX).not.toContain("allow-same-origin");
    expect(FRAME_SANDBOX).not.toContain("allow-top-navigation");
  });
  it("wraps the html and reports its own height under the frame's id", () => {
    const doc = frameDoc("<b>hi</b>", "f1");
    expect(doc).toContain("<b>hi</b>");
    expect(doc).toContain('"f1"');
    expect(doc).toContain("postMessage");
    expect(doc).toContain('<base target="_blank">');
  });
  it("cannot be broken out of through the id", () => {
    const doc = frameDoc("x", '"</script><script>alert(1)</script>');
    expect(doc.match(/<script>/g)).toHaveLength(1);
    expect(doc).toContain("\\u003c/script>");
  });
});

describe("a height message", () => {
  it("is accepted only for this frame's id", () => {
    expect(frameHeight({ opengenieFrame: "f1", height: 120 }, "f1")).toBe(120);
    expect(frameHeight({ opengenieFrame: "other", height: 120 }, "f1")).toBeNull();
  });
  it("is clamped to a sane range and rounded up", () => {
    expect(frameHeight({ opengenieFrame: "f1", height: 3 }, "f1")).toBe(MIN_FRAME);
    expect(frameHeight({ opengenieFrame: "f1", height: 99_999 }, "f1")).toBe(MAX_FRAME);
    expect(frameHeight({ opengenieFrame: "f1", height: 100.2 }, "f1")).toBe(101);
  });
  it("ignores anything that is not a finite number", () => {
    for (const bad of [null, "x", 5, {}, { opengenieFrame: "f1", height: "9" }, { opengenieFrame: "f1", height: NaN },
      { opengenieFrame: "f1", height: Infinity }]) {
      expect(frameHeight(bad, "f1")).toBeNull();
    }
  });
});
