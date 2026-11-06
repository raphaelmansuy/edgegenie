/** Minimal, safe markdown: headings, lists, tables, code, bold, inline code. No raw HTML, ever. */
import { useContext, type ReactNode } from "react";
import { splitPaths, workspaceUrl, type Workspace } from "../domain/links";
import { WorkspaceLinks } from "./DocContext";

const escape = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

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
export function Markdown({ text }: { text: string }) {
  const ws = useContext(WorkspaceLinks);
  if (!text) return null;
  const blocks: ReactNode[] = [];
  const lines = escape(text).split("\n");
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) { body.push(lines[i]); i += 1; }
      i += 1;
      blocks.push(<pre key={`k${key++}`}><code>{body.join("\n")}</code></pre>);
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
          <thead><tr>{head.map((h, n) => <th key={n}>{inline(h, `h${n}`, ws)}</th>)}</tr></thead>
          <tbody>{rows.map((r, rn) => <tr key={rn}>{r.map((c, cn) => <td key={cn}>{inline(c, `c${rn}${cn}`, ws)}</td>)}</tr>)}</tbody>
        </table>,
      );
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const level = Math.min(h[1].length, 4);
      const Tag = (`h${level}` as unknown) as "h2";
      blocks.push(<Tag key={`k${key++}`}>{inline(h[2], `h${key}`, ws)}</Tag>);
      i += 1;
      continue;
    }
    if (/^\s*([-*]|\d+[.)])\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*]|\d+[.)])\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*]|\d+[.)])\s+/, ""));
        i += 1;
      }
      blocks.push(<ul key={`k${key++}`}>{items.map((it, n) => <li key={n}>{inline(it, `i${n}`, ws)}</li>)}</ul>);
      continue;
    }
    if (line.trim() === "") { i += 1; continue; }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() !== "" && !/^\s*([-*]|\d+[.)])\s+/.test(lines[i])
      && !/^#{1,4}\s/.test(lines[i]) && !/^\s*\|/.test(lines[i]) && !/^\s*```/.test(lines[i])) {
      para.push(lines[i]);
      i += 1;
    }
    blocks.push(<p key={`k${key++}`}>{inline(para.join(" "), `p${key}`, ws)}</p>);
  }
  return <div className="answer">{blocks}</div>;
}
