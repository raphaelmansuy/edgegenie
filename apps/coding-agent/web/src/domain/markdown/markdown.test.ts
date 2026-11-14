import { describe, expect, it } from "vitest";
import { parseMarkdown, MARKDOWN_LIMITS } from "./parse";
import { destination, headingId } from "./policy";
import { formatSource } from "./format";
import { rasterSize } from "./media";

describe("Markdown source policy", () => {
  it.each(["javascript:alert(1)","java%73cript:alert(1)","data:image/svg+xml,<svg/>","//tracker.test/x","https://user:secret@example.com/x","https://example.com/%0aheader","file:///tmp/file","blob:https://example.com/x","http://example.com","https://example.com/\\evil"])("blocks %s", raw => expect(destination(raw).kind).toBe("blocked"));
  it.each([["https://example.com/a%20b","external"],["mailto:user@example.test","email"],["/Workspace/Users/me/plot.png","workspace"],["/Volumes/c/s/v/a.png","volume"],["#heading","fragment"]])("classifies %s", (raw, kind) => expect(destination(raw).kind).toBe(kind));
  it("resolves relative paths and encoded traversal before requests", () => {
    expect(destination("../images/chart.png", "/Users/me/notebooks/demo").value).toBe("/Users/me/images/chart.png");
    expect(destination("../../../../plot.png", "/Users/me/demo").kind).toBe("blocked");
    expect(destination("/Workspace/a/%2e%2e/image%20one.png").value).toBe("/Workspace/image one.png");
    expect(headingId("document:cell-a",0)).not.toBe(headingId("document:cell-b",0));
  });
});

describe("Atomic Markdown source edits", () => {
  it.each(["bold","italic","code"] as const)("wraps and selects exactly the chosen text for %s", command => {
    const edit = formatSource("A 😀 value", 2, 4, command);
    const updated = "A 😀 value".slice(0,edit.from)+edit.insert+"A 😀 value".slice(edit.to);
    expect(updated.slice(edit.anchor,edit.head)).toBe("😀");
  });
  it("toggles a matching wrapper and chooses a safe code delimiter", () => {
    expect(formatSource("**value**",0,9,"bold").insert).toBe("value");
    expect(formatSource("a`b",0,3,"code").insert).toBe("``a`b``");
    expect(formatSource("`value`",0,7,"code").insert).toBe("value");
    expect(formatSource("`edge",0,5,"code").insert).toBe("`` `edge ``");
  });
  it("formats selected complete lines without changing following lines", () => {
    expect(formatSource("one\ntwo\nthree",0,8,"quote")).toMatchObject({from:0,to:7,insert:"> one\n> two"});
    expect(formatSource("## Existing",0,11,"h1").insert).toBe("# Existing");
  });
  it("escapes link labels and destinations without touching unrelated source", () => {
    expect(formatSource("label",0,5,"link",{label:"a]b",url:"https://example.com/a(b)"}).insert).toBe("[a\\]b](https://example.com/a%28b%29)");
  });
});

describe("Bounded Markdown model", () => {
  it("retains six levels and duplicate heading entries", () => {
    expect(parseMarkdown("# Same\n\n## Same\n\n###### Detail").headings.map(h=>[h.ordinal,h.depth,h.label])).toEqual([[0,1,"Same"],[1,2,"Same"],[2,6,"Detail"]]);
  });
  it("keeps literal private-use markers from forging math indexes", () => {
    const model=parseMarkdown("\uE000999\uE001 then $x$");
    expect(model.issue).toBeUndefined();expect(model.spans).toHaveLength(1);
  });
  it("bounds source and nesting and always terminates on incomplete prefixes", () => {
    expect(parseMarkdown("x".repeat(MARKDOWN_LIMITS.chars+1)).issue).toBeTruthy();
    const input="# Title\n\n| a | b |\n|---|---|\n| `x` | $y$ |\n\n~~~sql\nselect 1\n~~~\n\n- **value**";
    for(let i=0;i<=input.length;i++)expect(parseMarkdown(input.slice(0,i)).tree.type).toBe("root");
    expect(parseMarkdown("> ".repeat(100)+"text").issue).toBeTruthy();
  });
  it("parses adversarial 20k delimiter inputs within a bounded working set", () => {
    for(const input of ["*a".repeat(10000),"[$".repeat(10000),"`\\".repeat(10000)]) expect(parseMarkdown(input).tree.type).toBe("root");
  });
  it("rejects non-raster data before decoding", () => expect(()=>rasterSize(new TextEncoder().encode('<svg/>'))).toThrow(/PNG and JPEG/));
});
