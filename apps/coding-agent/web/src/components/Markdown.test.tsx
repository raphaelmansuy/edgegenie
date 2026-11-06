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
