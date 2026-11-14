/** Shared AST renderer. Surface profiles control presentation, never source or persistence. */
import { Component, createElement, memo, useContext, useId, useMemo, type ReactNode } from "react";
import type { Nodes, Table } from "mdast";
import { parseMarkdown } from "../domain/markdown/parse";
import { destination, headingId, headingSlug } from "../domain/markdown/policy";
import { splitStashed } from "../domain/math";
import { splitPaths, workspaceUrl } from "../domain/links";
import { WorkspaceLinks, OpenSqlQuery } from "./DocContext";
import { Math as MathNode } from "./Math";
import { CopyButton } from "./CopyButton";
import { MarkdownImage } from "./MarkdownImage";
import "../notebook-markdown.css";
import type { MarkdownModel } from "../domain/markdown/parse";

export interface MarkdownProps { text: string; streaming?: boolean; surface?: "answer" | "notebook"; namespace?: string; documentPath?: string; model?: MarkdownModel }
class RenderBoundary extends Component<{ text: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidUpdate(previous: { text: string }) { if (previous.text !== this.props.text && this.state.failed) this.setState({ failed: false }); }
  render() { return this.state.failed ? <Fallback text={this.props.text} reason="This preview could not be rendered." /> : this.props.children; }
}
function Fallback({ text, reason }: { text: string; reason: string }) {
  return <div className="markdown-fallback" role="region" aria-label="Preview unavailable"><p role="status">Preview unavailable. {reason}</p><CopyButton text={text} label="Copy source" /><pre>{text.slice(0, 20_000)}</pre></div>;
}
function MarkdownView({ text, streaming = false, surface = "answer", namespace, documentPath = "", model: suppliedModel }: MarkdownProps) {
  const generatedId = useId();
  const ns = namespace || generatedId;
  const ws = useContext(WorkspaceLinks);
  const openSql = useContext(OpenSqlQuery);
  const model = useMemo(() => suppliedModel ?? parseMarkdown(text), [text, suppliedModel]);
  const definitions = useMemo(() => new Map(model.tree.children.filter(n => n.type === "definition").map(n => [n.identifier.toLowerCase(), n])), [model]);
  if (!text.trim()) return surface === "notebook" ? <div className="notebook-markdown is-empty"><p>Empty Markdown cell</p></div> : null;
  if (model.issue) return <Fallback text={text} reason={model.issue} />;
  const linked = (value: string, key: string): ReactNode => splitPaths(value).map((p, i) => {
    const href = p.path ? workspaceUrl(ws, { kind: "file", ref: p.path }) : null;
    return href ? <a key={`${key}-${i}`} className="path-link" href={href} target="_blank" rel="noopener noreferrer">{p.text}</a> : p.text;
  });
  const textNodes = (value: string, key: string): ReactNode => splitStashed(value).map((p, i) => p.kind === "text"
    ? <span key={`${key}-${i}`}>{linked(p.text, key + i)}</span>
    : model.spans[p.index] ? <MathNode key={`${key}-${i}`} span={model.spans[p.index]} streaming={streaming} /> : null);
  let heading = 0;
  const link = (raw: string, body: ReactNode, key: string, title?: string | null) => {
    const d = destination(raw, documentPath);
    if (d.kind === "fragment") {
      const target = model.headings.find(h => headingSlug(h.label) === decodeURIComponent(raw.slice(1)));
      if (!target) return <span key={key} title="Heading not found">{body}</span>;
      const id = headingId(ns, target.ordinal);
      return <a key={key} href={`#${id}`} onClick={e => { e.preventDefault(); const node = document.getElementById(id); node?.scrollIntoView({ block: "start" }); node?.focus({ preventScroll: true }); }}>{body}</a>;
    }
    const href = d.kind === "workspace" ? workspaceUrl(ws, { kind: "file", ref: d.value }) : d.kind === "external" || d.kind === "email" ? d.value : null;
    return href ? <a key={key} href={href} title={title ?? undefined} target={d.kind === "email" ? undefined : "_blank"} rel="noopener noreferrer">{body}</a>
      : <span key={key} className="markdown-unsupported-link" title={d.reason || "This destination is unavailable"}>{body}</span>;
  };
  const render = (n: Nodes, key: string, table?: Table): ReactNode => {
    const children = () => "children" in n ? n.children.map((c, i) => render(c as Nodes, `${key}-${i}`, table)) : null;
    switch (n.type) {
      case "root": return children();
      case "text": return textNodes(n.value, key);
      case "paragraph": {
        const only = n.children.length === 1 && n.children[0].type === "text" ? splitStashed(n.children[0].value) : [];
        if (only.length === 1 && only[0].kind === "math" && model.spans[only[0].index]?.mode === "display") return <div key={key} className="math-block">{children()}</div>;
        return <p key={key}>{children()}</p>;
      }
      case "heading": {
        const ordinal = heading++;
        // Notebook has its own document outline; visual source depth remains independent.
        const level = surface === "notebook" ? n.depth + 1 : Math.max(2, n.depth);
        return createElement(`h${Math.min(6, level)}`, { key, id: headingId(ns, ordinal), tabIndex: -1,
          "data-heading-depth": n.depth, "aria-level": level > 6 ? level : undefined }, children());
      }
      case "strong": return <strong key={key}>{children()}</strong>;
      case "emphasis": return <em key={key}>{children()}</em>;
      case "delete": return <del key={key}>{children()}</del>;
      case "inlineCode": return <code key={key}>{linked(n.value, key)}</code>;
      case "break": return <br key={key} />;
      case "thematicBreak": return <hr key={key} />;
      case "blockquote": return <blockquote key={key}>{children()}</blockquote>;
      case "list": return n.ordered ? <ol key={key} start={n.start ?? 1}>{children()}</ol> : <ul key={key}>{children()}</ul>;
      case "listItem": return <li key={key} className={typeof n.checked === "boolean" ? "markdown-task-item" : undefined}>{n.checked !== null && n.checked !== undefined && <input type="checkbox" checked={n.checked} disabled aria-label={n.checked ? "Completed item" : "Incomplete item"} />}{children()}</li>;
      case "link": return link(n.url, children(), key, n.title);
      case "linkReference": { const d = definitions.get(n.identifier.toLowerCase()); return d ? link(d.url, children(), key, d.title) : <span key={key}>{children()}</span>; }
      case "image": return <MarkdownImage key={key} source={n.url} alt={n.alt ?? ""} documentPath={documentPath} />;
      case "imageReference": { const d = definitions.get(n.identifier.toLowerCase()); return <MarkdownImage key={key} source={d?.url ?? ""} alt={n.alt ?? ""} documentPath={documentPath} />; }
      case "code": return <figure key={key} className="codeblock"><figcaption><span className="codeblock-lang">{n.lang || "code"}</span>
        {surface === "answer" && n.lang?.toLowerCase() === "sql" && openSql && <button className="sql-promote-button" disabled={streaming} onClick={() => openSql(n.value)}>Open as query</button>}
        <CopyButton text={n.value} label="Copy" title="Copy this code" /></figcaption><pre><code>{n.value}</code></pre></figure>;
      case "table": return <div key={key} className="markdown-table-scroll" role="region" aria-label="Markdown table" tabIndex={0}><table><thead><tr>{n.children[0]?.children.map((c, i) => <th key={i} scope="col" style={{ textAlign: n.align?.[i] ?? undefined }}>{c.children.map((x, j) => render(x as Nodes, `${key}-h${i}-${j}`))}</th>)}</tr></thead><tbody>{n.children.slice(1).map((row, i) => <tr key={i}>{n.children[0].children.map((_, j) => <td key={j} style={{ textAlign: n.align?.[j] ?? undefined }}>{row.children[j]?.children.map((c, k) => render(c as Nodes, `${key}-${i}-${j}-${k}`))}</td>)}</tr>)}</tbody></table></div>;
      case "html": return <span key={key} className="markdown-literal">{n.value}</span>;
      case "definition": return null;
      default: return <span key={key}>{"value" in n ? String(n.value) : children()}</span>;
    }
  };
  return <div className={`answer markdown-document${surface === "notebook" ? " notebook-markdown" : ""}`}>{render(model.tree, "root")}</div>;
}
export const Markdown = memo(function Markdown(props: MarkdownProps) { return <RenderBoundary text={props.text}><MarkdownView {...props} /></RenderBoundary>; });
