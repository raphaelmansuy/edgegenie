import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("renders headings, lists, tables and code", () => {
    const { container } = render(<Markdown text={"## Evidence\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |"} />);
    expect(container.querySelector("h2")?.textContent).toBe("Evidence");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelectorAll("th")).toHaveLength(2);
  });

  it("never executes HTML from the model", () => {
    const { container } = render(<Markdown text={"hello <script>alert('x')</script>"} />);
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText(/alert/)).toBeTruthy();
  });

  it("renders a javascript: link as text, not as a link", () => {
    const { container } = render(<Markdown text={"[click](javascript:alert(1))"} />);
    expect(container.querySelector("a")).toBeNull();
  });

  // Regression: "Page Unresponsive". A streamed answer is a sequence of PREFIXES, and a prefix that ends
  // mid-table-row ("| requirement | tool | summ") was declined by the table branch and excluded by the
  // paragraph branch, so the parser never advanced. Every prefix of a document must render.
  it("renders every prefix of a streamed document (a stream is a sequence of prefixes)", () => {
    const doc = [
      "## Result", "", "Done with `code` and **bold** in /Shared/x/y.", "",
      "| requirement | tool | summary |", "|---|---|---|", "| do the work | dbx_run_sql | 3 rows |", "",
      "- one", "2. two", "#### ", "# ", "|", "| lone row", "||", "```sql", "select 1", "```", "***", "`", "**",
      "EVIDENCE", "", "| a | b |", "| c |",
    ].join("\n");
    for (let n = 0; n <= doc.length; n++) {
      const { unmount, container } = render(<Markdown text={doc.slice(0, n)} />);
      expect(container.querySelectorAll("p").length).toBeLessThanOrEqual(n);   // never an unbounded pile
      unmount();
    }
  });

  it("a half-finished table row is shown as text, not lost and not looped on", () => {
    const { container } = render(<Markdown text={"Intro\n\n| requirement | tool | summ"} />);
    expect(container.textContent).toContain("| requirement | tool | summ");
  });

  // Regression: the text was HTML-escaped and then escaped again by React, so SQL showed as `a &lt; b`.
  it("shows < > & exactly as written, in prose and in code", () => {
    const { container } = render(<Markdown text={"Rows where a < b && c > d.\n\n```sql\nselect * from t where a < 1 and b > 2 -- &\n```"} />);
    expect(container.querySelector("p")?.textContent).toBe("Rows where a < b && c > d.");
    expect(container.querySelector("pre code")?.textContent).toBe("select * from t where a < 1 and b > 2 -- &");
    expect(container.innerHTML).not.toContain("&amp;lt;");
  });

  it("labels a code block with its language and offers Copy", () => {
    const { container } = render(<Markdown text={"```python\nprint(1)\n```\n\n```\nplain\n```"} />);
    const langs = [...container.querySelectorAll(".codeblock-lang")].map((n) => n.textContent);
    expect(langs).toEqual(["python", "code"]);
    expect(container.querySelectorAll(".codeblock .copy-btn")).toHaveLength(2);
  });

  it("uses code blocks for fenced content", () => {
    const { container } = render(<Markdown text={"```sql\nselect 1\n```"} />);
    expect(container.querySelector("pre code")?.textContent).toBe("select 1");
  });
});

import { WorkspaceLinks } from "./DocContext";
describe("Markdown links into the workspace", () => {
  const ws = { host: "https://dbc-1.cloud.databricks.com" };
  it("turns a workspace path, in prose or in code, into a link", () => {
    const { container } = render(
      <WorkspaceLinks.Provider value={ws}>
        <Markdown text={"Wrote /Users/a@b.c/agent_scratch/hello_world. Also `/Shared/x`."} />
      </WorkspaceLinks.Provider>);
    const hrefs = Array.from(container.querySelectorAll("a.path-link")).map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual([
      "https://dbc-1.cloud.databricks.com/#workspace/Users/a%40b.c/agent_scratch/hello_world",
      "https://dbc-1.cloud.databricks.com/#workspace/Shared/x",
    ]);
    expect(container.querySelector("a.path-link")?.getAttribute("rel")).toContain("noopener");
  });
  it("adds no links without a workspace, and still shows the path", () => {
    const { container } = render(<Markdown text={"Wrote /Users/a/x"} />);
    expect(container.querySelectorAll("a").length).toBe(0);
    expect(container.textContent).toContain("/Users/a/x");
  });
});
