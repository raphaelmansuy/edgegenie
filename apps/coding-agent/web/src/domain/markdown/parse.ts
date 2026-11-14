/** One grammar for notebook, file and chat surfaces. Parsed data never becomes saved source. */
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import type { Root, RootContent, Nodes } from "mdast";
import { stashMath, splitStashed, type MathSpan } from "../math";

const parser = unified().use(remarkParse).use(remarkGfm, { singleTilde: false });
// Bare workspace paths often contain email addresses. Do not split those into mailto nodes.
parser.data("micromarkExtensions", [{ disable: { null: ["emailAutolink"] } }]);
export const MARKDOWN_LIMITS = { chars: 200_000, nodes: 10_000, depth: 64, math: 200 };
export interface Heading { ordinal: number; depth: number; label: string }
export interface MarkdownModel { tree: Root; spans: MathSpan[]; headings: Heading[]; issue?: string }

function plain(node: Nodes, spans: MathSpan[]): string {
  if (node.type === "text") return splitStashed(node.value).map(p => p.kind === "text" ? p.text : spans[p.index]?.tex ?? "").join("");
  if ("value" in node) return String(node.value);
  return "children" in node ? node.children.map(n => plain(n as Nodes, spans)).join("") : "";
}

export function parseMarkdown(text: string): MarkdownModel {
  const empty: Root = { type: "root", children: [] };
  if (text.length > MARKDOWN_LIMITS.chars) return { tree: empty, spans: [], headings: [], issue: "This text exceeds the preview size limit." };
  try {
    const { prose, spans } = stashMath(text);
    if (spans.length > MARKDOWN_LIMITS.math) throw new Error("Too many equations for one preview.");
    const tree = parser.parse(prose) as Root;
    const headings: Heading[] = [];
    const stack: { node: Nodes; depth: number }[] = [{ node: tree, depth: 0 }];
    let count = 0;
    while (stack.length) {
      const { node, depth } = stack.pop()!;
      if (++count > MARKDOWN_LIMITS.nodes || depth > MARKDOWN_LIMITS.depth) throw new Error("This content exceeds the preview complexity limit.");
      if ("children" in node) {
        // GFM's post-parse bare-email expansion splits /Users/name@example.com paths.
        // Explicit links have positions. Keep automatic bare text as text, then join its pieces.
        const parent = node as unknown as { children: Nodes[] };
        const children: Nodes[] = [];
        for (const child of parent.children) {
          const next: Nodes = child.type === "link" && !child.position ? { type: "text", value: plain(child, spans) } : child;
          const previous = children.at(-1);
          if (next.type === "text" && previous?.type === "text") previous.value += next.value;
          else children.push(next);
        }
        parent.children = children;
      }
      if (node.type === "heading") headings.push({ ordinal: headings.length, depth: node.depth, label: plain(node, spans) });
      if ("children" in node) for (let i = node.children.length - 1; i >= 0; i--) stack.push({ node: node.children[i] as Nodes, depth: depth + 1 });
    }
    return { tree, spans, headings };
  } catch (e) {
    return { tree: empty, spans: [], headings: [], issue: e instanceof Error ? e.message : "This preview could not be rendered." };
  }
}

export type MarkdownNode = RootContent | Nodes;
