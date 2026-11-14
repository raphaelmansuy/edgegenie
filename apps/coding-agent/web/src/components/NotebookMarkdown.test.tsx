import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Markdown } from "./Markdown";
import { NotebookEditor } from "./NotebookEditor";
import { newCell } from "../domain/notebook";
afterEach(cleanup);

it("renders styled notebook semantics while preserving source heading depth", () => {
  const {container}=render(<Markdown surface="notebook" text={"# Title\n\n## Section\n\n### Detail\n\n*emphasis* and ~~old~~\n\n3. third\n4. fourth\n\n> quote\n\n- [x] done"} />);
  expect(container.querySelector('[data-heading-depth="1"]')?.tagName).toBe("H2");
  expect(container.querySelector('[data-heading-depth="2"]')?.tagName).toBe("H3");
  expect(container.querySelector('em')?.textContent).toBe("emphasis");
  expect(container.querySelector('del')?.textContent).toBe("old");
  expect(container.querySelector('ol')).toHaveAttribute('start','3');
  expect(container.querySelector('blockquote')).toHaveTextContent('quote');
  expect(screen.getByRole('checkbox')).toBeDisabled();
});
it("does not execute HTML or reinterpret literal PUA as a math span", () => {
  const {container}=render(<Markdown surface="notebook" text={'<script>alert(1)</script>\n\n\uE000999\uE001 then $x$\n\n[bad](javascript:alert(1))'} />);
  expect(container.querySelector('script')).toBeNull();expect(container.querySelector('a')).toBeNull();
  expect(container.textContent).toContain('\uE000999\uE001');
});
it("shows all resting Markdown cells as content including empty and readonly cells", () => {
  const onChange=vi.fn();
  const {container}=render(<NotebookEditor cells={[newCell('markdown','markdown','# Readable'),newCell('markdown','markdown','')]} language="PYTHON" theme="light" readOnly onChange={onChange} />);
  expect(screen.getByText('Readable')).toBeVisible();expect(screen.getByText('Empty Markdown cell')).toBeVisible();
  expect(container.querySelector('.editor-host')).toBeNull();expect(screen.queryByRole('button',{name:/Edit Markdown/})).toBeNull();
  fireEvent.doubleClick(screen.getByText('Readable'));expect(onChange).not.toHaveBeenCalled();
});
it("does not fetch an image on render and exposes its description", () => {
  const fetcher=vi.spyOn(globalThis,'fetch');
  render(<Markdown surface="notebook" documentPath="/Users/me/notebook" text="![Revenue chart](./chart.png)" />);
  expect(screen.getByRole('group',{name:'Revenue chart'})).toBeVisible();expect(screen.getByRole('button',{name:'Load image'})).toBeEnabled();
  expect(fetcher).not.toHaveBeenCalled();fetcher.mockRestore();
});
it("renders escaped table pipes and tilde fences without a notebook query action", () => {
  const {container}=render(<Markdown surface="notebook" text={'| a | b |\n|:--|--:|\n| x \\| y | 2 |\n\n~~~sql\nselect 1\n~~~'} />);
  expect(container.querySelector('td')).toHaveTextContent('x | y');expect(container.querySelector('pre code')).toHaveTextContent('select 1');
  expect(screen.queryByRole('button',{name:'Open as query'})).toBeNull();
});
