/** Markdown for answers and markdown cells: headings, lists, tables, code, emphasis, inline code,
 *  links, and **math** (TeX via KaTeX). No raw HTML, ever.
 *
 * Math is the one part that cannot be a regex in `inline()`: `$` is also money, `\$` is an escape, and
 * a formula inside a fenced block is code. `domain/math.ts` finds the spans as data (with the rules and
 * its own tests); this file stashes them behind a private-use marker so the ordinary markdown pass runs
 * unchanged, then substitutes the rendered <Math> back in. That keeps one parser and one code path for
 * a streamed answer and a finished one.
 */
import { memo, useContext, useMemo, type ReactNode } from "react";
import { splitStashed, stashMath, type MathSpan } from "../domain/math";
import { Math as MathNode } from "./Math";
import { splitPaths, workspaceUrl, type Workspace } from "../domain/links";
import { WorkspaceLinks } from "./DocContext";
import { CopyButton } from "./CopyButton";

/** A workspace path becomes a link to that object in Databricks; anything else stays text. */
function linked(text: string, ws: Workspace | null, keyBase: string, asCode = false): ReactNode[] {
  if (!ws) return [asCode ? <code key={`${keyBase}-x`}>{text}</code> : text];
  return splitPaths(text).map((part, n) => {
    const href = part.path ? workspaceUrl(ws, { kind: "file", ref: part.path }) : null;
    const body = asCode ? <code>{part.text}</code> : part.text;
    return href
      ? <a key={`${keyBase}-l${n}`} className="path-link" href={href} target="_blank" rel="noopener noreferrer"
          title="Open in Databricks">{body}</a>
      : <span key={`${keyBase}-t${n}`}>{body}</span>;
  });
}

/** The stashed-marker pass for INLINE text (a paragraph, a table cell, a list item, a heading).
 *  Display math inside a paragraph is unusual but legal; it renders in place, as its own block. */
function inlineStashed(text: string, keyBase: string, ws: Workspace | null, spans: MathSpan[], streaming: boolean): ReactNode[] {
  const parts = splitStashed(text);
  if (parts.length === 0) return [];
  const out: ReactNode[] = [];
  parts.forEach((part, n) => {
    if (part.kind === "math") {
      out.push(<MathNode key={`${keyBase}-m${n}`} span={spans[part.index]} streaming={streaming} />);
      return;
    }
    out.push(...inline(part.text, `${keyBase}-t${n}`, ws));
  });
  return out;
}

function inline(text: string, keyBase: string, ws: Workspace | null = null): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(...linked(text.slice(last, m.index), ws, `${keyBase}-p${i}`));
    const tok = m[0];
    if (tok.startsWith("`")) {
      const code = tok.slice(1, -1);
      out.push(ws && splitPaths(code).some((p) => p.path)
        ? <span key={`${keyBase}-c${i}`}>{linked(code, ws, `${keyBase}-c${i}`, true)}</span>
        : <code key={`${keyBase}-c${i}`}>{code}</code>);
    }
    else out.push(<strong key={`${keyBase}-b${i}`}>{tok.slice(2, -2)}</strong>);
    last = m.index + tok.length;
    i += 1;
  }
  if (last < text.length) out.push(...linked(text.slice(last), ws, `${keyBase}-end`));
  return out;
}

/** Renders a markdown subset. Any HTML in the input is displayed as text, never executed. */
function MarkdownView({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const ws = useContext(WorkspaceLinks);
  /* One stash for the whole document: offsets stay consistent and a fence's `$` is already excluded by
     `findMath`, so the markdown pass below never sees a delimiter. */
  const { prose, spans } = useMemo(() => stashMath(text), [text]);
  const inlineText = (s: string, k: string) => inlineStashed(s, k, ws, spans, streaming);
  if (!text) return null;
  const blocks: ReactNode[] = [];
  /* No manual HTML escaping: this renders React text nodes, which React escapes, and nothing here uses
     `dangerouslySetInnerHTML`. Escaping first double-encoded the text, so "a < b" showed as "a &lt; b". */
  /* `prose`, not `text`: every `$...$` is a marker by now, so no markdown rule can see a delimiter and
     the math is substituted back only at the leaves. */
  const lines = prose.split("\n");
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    const fence = /^\s*```\s*([\w+#.-]*)/.exec(line);
    if (fence) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) { body.push(lines[i]); i += 1; }
      i += 1;
      const code = body.join("\n");
      blocks.push(
        <figure key={`k${key++}`} className="codeblock">
          <figcaption>
            <span className="codeblock-lang">{fence[1] || "code"}</span>
            <CopyButton text={code} label="Copy" title="Copy this code" />
          </figcaption>
          <pre><code>{code}</code></pre>
        </figure>,
      );
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const head = line.split("|").slice(1, -1).map((c) => c.trim());
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        rows.push(lines[i].split("|").slice(1, -1).map((c) => c.trim()));
        i += 1;
      }
      blocks.push(
        <table key={`k${key++}`}>
          <thead><tr>{head.map((h, n) => <th key={n}>{inlineText(h, `h${n}`)}</th>)}</tr></thead>
          <tbody>{rows.map((r, rn) => <tr key={rn}>{r.map((c, cn) => <td key={cn}>{inlineText(c, `c${rn}${cn}`)}</td>)}</tr>)}</tbody>
        </table>,
      );
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      /* A `#` in a document is not the page's title — the page already has one (`h1.brand`), and this
         markdown renders inside it. Emitting `<h1>` for `# e2e seed` gave the document screen two
         level-one headings, which breaks the outline a screen reader navigates by (measured: h1 count:
         2). Only the TOP level moves, from h1 to h2; `## …` stays h2 and `### …` stays h3, so the
         outline below the first line keeps the depth the author wrote. */
      const level = Math.max(2, Math.min(h[1].length, 4));
      const Tag = (`h${level}` as unknown) as "h2";
      blocks.push(<Tag key={`k${key++}`}>{inlineText(h[2], `h${key}`)}</Tag>);
      i += 1;
      continue;
    }
    if (/^\s*([-*]|\d+[.)])\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*]|\d+[.)])\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*]|\d+[.)])\s+/, ""));
        i += 1;
      }
      blocks.push(<ul key={`k${key++}`}>{items.map((it, n) => <li key={n}>{inlineText(it, `i${n}`)}</li>)}</ul>);
      continue;
    }
    if (line.trim() === "") { i += 1; continue; }
    /* The first line is taken unconditionally. Every branch above declined it, so it is prose by
       definition; the `while` below only decides where the paragraph ENDS. Without this, a line the
       table branch declined (a row that starts with "|" but is not finished, which is exactly what a
       streamed table looks like mid-row) was also excluded here, consumed nothing, and `i` never
       advanced: an infinite loop pushing empty <p> elements until the tab died ("Page Unresponsive"). */
    const para: string[] = [lines[i]];
    i += 1;
    while (i < lines.length && lines[i].trim() !== "" && !/^\s*([-*]|\d+[.)])\s+/.test(lines[i])
      && !/^#{1,4}\s/.test(lines[i]) && !/^\s*\|/.test(lines[i]) && !/^\s*```/.test(lines[i])) {
      para.push(lines[i]);
      i += 1;
    }
    /* A paragraph that is nothing but a DISPLAY formula becomes a block, not a paragraph holding a
       centred formula: that is what `$$...$$` means, and it is how the answer's rhythm stays right. */
    const joined = para.join(" ").trim();
    const onlyMath = splitStashed(joined);
    if (onlyMath.length === 1 && onlyMath[0].kind === "math" && spans[onlyMath[0].index].mode === "display") {
      blocks.push(
        <div key={`k${key++}`} className="math-block">
          <MathNode span={spans[onlyMath[0].index]} streaming={streaming} />
        </div>,
      );
      continue;
    }
    blocks.push(<p key={`k${key++}`}>{inlineText(joined, `p${key}`)}</p>);
  }
  return <div className="answer">{blocks}</div>;
}

/** Markdown parsing is the expensive part of a streamed answer: re-parse only when the text changes. */
export const Markdown = memo(MarkdownView);
