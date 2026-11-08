import { describe, expect, it } from "vitest";
import { isFocusable, successor } from "./useReturnFocus";

const mount = (html: string) => {
  document.body.innerHTML = html;
  return document.body;
};

describe("isFocusable: usable, not merely present (E-37)", () => {
  it("accepts a visible button and rejects a disconnected one", () => {
    const b = document.createElement("button");
    document.body.appendChild(b);
    // jsdom reports no layout, so offsetParent is null for everything: the check must not reject a
    // real, in-document control on that basis alone.
    expect(isFocusable(b)).toBe(true);
    b.remove();
    expect(isFocusable(b)).toBe(false);
  });
  it("rejects a disabled control and a non-element", () => {
    const b = document.createElement("button");
    b.setAttribute("disabled", "");
    document.body.appendChild(b);
    expect(isFocusable(b)).toBe(false);
    expect(isFocusable(null)).toBe(false);
    expect(isFocusable(document.createTextNode("x") as never)).toBe(false);
  });
});

describe("successor: a named region, never body (KB-1)", () => {
  it("prefers the selected tab, then the composer, then main", () => {
    mount(`<div role="tab" aria-selected="true" tabindex="0">tab</div>
           <div class="composer"><textarea></textarea></div>
           <main tabindex="-1"></main>`);
    expect(successor()?.getAttribute("role")).toBe("tab");
    document.querySelector('[role="tab"]')!.remove();
    expect(successor()?.tagName.toLowerCase()).toBe("textarea");
    document.querySelector(".composer")!.remove();
    expect(successor()?.tagName.toLowerCase()).toBe("main");
  });
  it("returns null rather than falling back to body", () => {
    mount("");
    expect(successor()).toBeNull();
  });
});
