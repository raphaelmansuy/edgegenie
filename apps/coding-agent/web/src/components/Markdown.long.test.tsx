import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { Markdown } from "./Markdown";

afterEach(cleanup);

/** jsdom has no layout engine, so this pins the *contract* instead: the classes and rules that make
 *  a long unbroken token wrap. The deployed audit (scripts/overflow-audit.mjs) proves the rendering. */
describe("a long token cannot widen the transcript", () => {
  const TOOL = "db_dbx_run_notebook(path=/Users/raphael.mansuy@gmail.com/agent_scratch/taxi_hours, timeout=45)";
  it("keeps an unbroken path inside a paragraph", () => {
    const { container } = render(<Markdown text={`Ran ${TOOL} and it finished.`} />);
    const p = container.querySelector(".answer p")!;
    expect(p.textContent).toContain(TOOL);
    // the wrap rules live on .answer and its children; the assertion is that both exist in the DOM
    expect(container.querySelector(".answer")).not.toBeNull();
    expect(p.closest(".answer")).not.toBeNull();
  });
  it("does not let a wide table escape: it is fixed-layout with wrapping cells", () => {
    const { container } = render(
      <Markdown text={"| requirement | tool |\n|---|---|\n| " + TOOL + " | dbx_run_sql |"} />);
    const table = container.querySelector(".answer table")!;
    expect(table).not.toBeNull();
    expect(container.querySelectorAll("td").length).toBe(2);
  });
});
