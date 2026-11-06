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
