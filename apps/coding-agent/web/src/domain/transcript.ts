/** A conversation as Markdown. Pure.
 *
 * Genie Code lets you take a conversation with you. The export is for people (a ticket, a review, a
 * handover), so it keeps the question, what the agent did in one line per tool, and the answer, and
 * drops the plumbing: no event ids, no token counts, no raw tool output.
 */
import type { Turn } from "./events";
import { stripEvidence, subject } from "./toolview";

const VERB: [RegExp, string][] = [
  [/write_(notebook|file)/, "wrote"], [/run_notebook/, "ran a notebook"], [/run_sql|query/, "ran SQL"],
  [/describe_table|read_table|sample/, "looked at a table"], [/read_(notebook|file)/, "read"],
];

function toolLine(name: string, args: string | undefined, status: string): string {
  const verb = VERB.find(([re]) => re.test(name))?.[1] ?? name.replace(/_/g, " ");
  const what = subject(args, 80);
  const tail = status === "error" ? " (failed)" : "";
  return `- ${verb}${what ? ` \`${what}\`` : ""}${tail}`;
}

export function conversationMarkdown(title: string, turns: Turn[], when?: Date): string {
  const lines: string[] = [`# ${title.trim() || "Conversation"}`];
  if (when) lines.push("", `_Exported ${when.toISOString().slice(0, 16).replace("T", " ")} UTC_`);
  for (const t of turns) {
    lines.push("", "## You", "", t.prompt.trim());
    if (t.tools.length) lines.push("", "### What the agent did", "", ...t.tools.map((c) => toolLine(c.name, c.args, c.status)));
    const answer = stripEvidence(t.answer).trim();
    if (answer) lines.push("", "## Agent", "", answer);
    if (t.status !== "completed") lines.push("", `_This turn ended ${t.status}._`);
  }
  return `${lines.join("\n")}\n`;
}

/** A safe file name for the download: the title, lower-cased, no path characters. */
export function exportName(title: string): string {
  const base = (title ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48);
  return `${base || "conversation"}.md`;
}
