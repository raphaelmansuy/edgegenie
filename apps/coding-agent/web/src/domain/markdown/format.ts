/** Pure source edits; offsets use the editor's UTF-16 coordinate system. */
export type Format = "bold" | "italic" | "code" | "h1" | "h2" | "h3" | "list" | "quote" | "link" | "image";
export interface SourceEdit { from: number; to: number; insert: string; anchor: number; head: number }
export function formatSource(source: string, start: number, end: number, command: Format, reference?: { label: string; url: string }): SourceEdit {
  const from = Math.max(0, Math.min(start, end, source.length));
  const to = Math.max(from, Math.min(Math.max(start, end), source.length));
  const picked = source.slice(from, to);
  if (["h1", "h2", "h3", "list", "quote"].includes(command)) {
    const a = source.lastIndexOf("\n", from - 1) + 1;
    const next = source.indexOf("\n", to > from && source[to - 1] === "\n" ? to - 1 : to);
    const b = next < 0 ? source.length : next;
    const prefix = command === "list" ? "- " : command === "quote" ? "> " : "#".repeat(Number(command.slice(1))) + " ";
    const lines = source.slice(a, b).split("\n");
    const matching = lines.every(line => line.startsWith(prefix));
    const insert = lines.map(line => matching ? line.slice(prefix.length) : prefix + (command.startsWith("h") ? line.replace(/^#{1,6}\s+/, "") : line)).join("\n");
    return { from: a, to: b, insert, anchor: a, head: a + insert.length };
  }
  if (command === "link" || command === "image") {
    const label = (reference?.label || picked || (command === "image" ? "Image description" : "Link text")).replace(/([\[\]\\])/g, "\\$1");
    const url = (reference?.url || "https://example.com").replace(/ /g, "%20").replace(/\(/g, "%28").replace(/\)/g, "%29");
    const insert = `${command === "image" ? "!" : ""}[${label}](${url})`;
    return { from, to, insert, anchor: from, head: from + insert.length };
  }
  let wrapper = command === "bold" ? "**" : command === "italic" ? "*" : "`";
  if (command === "code") {
    const existing = /^(`+)([^`][\s\S]*?[^`]|[^`])\1$/.exec(picked);
    if (existing) {
      const insert = existing[2].startsWith(" ") && existing[2].endsWith(" ") && /[^ ]/.test(existing[2]) ? existing[2].slice(1,-1) : existing[2];
      return { from, to, insert, anchor: from, head: from + insert.length };
    }
    const runs = picked.match(/`+/g) ?? [];
    wrapper = "`".repeat(Math.max(0, ...runs.map(run => run.length)) + 1);
  }
  if (picked.startsWith(wrapper) && picked.endsWith(wrapper) && picked.length >= wrapper.length * 2) {
    const insert = picked.slice(wrapper.length, -wrapper.length);
    return { from, to, insert, anchor: from, head: from + insert.length };
  }
  const content = picked || "text";
  const padding = command === "code" && (/^`|`$/.test(content) || /^ .* $/.test(content) && /[^ ]/.test(content)) ? " " : "";
  return { from, to, insert: wrapper + padding + content + padding + wrapper, anchor: from + wrapper.length + padding.length, head: from + wrapper.length + padding.length + content.length };
}
