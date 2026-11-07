#!/usr/bin/env node
/** Verify that the ASCII diagrams in a spec set are drawn on a consistent grid.
 *
 * A box one character out of alignment reads as broken, and the defect is invisible in a diff. This
 * parses each box rather than comparing line widths, so nested boxes and several boxes in one block
 * are handled correctly.
 *
 * For every `┌` in a fenced text/ascii block:
 *   - the top border runs to a `┐` on the same line, with nothing but `─` between;
 *   - some later line closes it with `└` at the same column and `┘` at the same right column;
 *   - every line strictly between has a vertical border at both columns;
 *   - the box is not crossed by a longer line that implies a different right edge.
 *
 * Run:  node scripts/verify-spec-ascii.mjs <dir>
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const dir = process.argv[2] ?? ".";
const files = readdirSync(dir).filter((f) => f.endsWith(".md")).sort();

const LEFT = new Set(["│", "├", "┌", "└", "┬", "┴", "┼"]);
const RIGHT = new Set(["│", "┤", "┐", "┘", "┬", "┴", "┼"]);
// An arrow landing on a border is normal drawing, not a defect: it marks an edge's source or target.
const ARROWS = new Set([..."▼▲▶◀"]);

let problems = 0;
let blocks = 0;
let boxes = 0;

const line = (s, i) => (i >= 0 && i < s.length ? s[i] : "");

function checkBox(rows, x, y, report) {
  const top = rows[y];
  let right = -1;
  for (let i = x + 1; i < top.length; i += 1) {
    if (top[i] === "┐") { right = i; break; }
    if ((top[i] !== "─" && top[i] !== "┬") && !ARROWS.has(top[i])) {
      report("TOP", y + 1, `top border of the box at column ${x} breaks at ${i} with "${top[i]}"`);
      return;
    }
  }
  if (right < 0) {
    report("UNCLOSED", y + 1, `no "┐" closes the box opened at column ${x}`);
    return;
  }
  boxes += 1;

  let close = -1;
  for (let j = y + 1; j < rows.length; j += 1) {
    if (line(rows[j], x) === "└" && line(rows[j], right) === "┘") { close = j; break; }
    // A `┌` at the same column before a `└` means a second box starts where this one should close.
    if (line(rows[j], x) === "┌") break;
  }
  if (close < 0) {
    report("UNCLOSED", y + 1, `box opened at column ${x} (width ${right - x + 1}) never closes`);
    return;
  }
  for (let j = y + 1; j < close; j += 1) {
    const l = line(rows[j], x);
    const r = line(rows[j], right);
    if (!LEFT.has(l) && !ARROWS.has(l)) report("LEFT", j + 1, `expected a left border at column ${x}, found "${l}"`);
    if (!RIGHT.has(r) && !ARROWS.has(r)) report("RIGHT", j + 1, `expected a right border at column ${right}, found "${r}"`);
    // Content that runs past the right border is only a defect if it is not itself drawing:
    // a nested box or a side-by-side panel legitimately extends further right.
    const after = rows[j].slice(right + 1).trimEnd();
    const drawingOnly = /^[│┤┐┘┬┴┼─\s]*$/.test(after);
    if (after && !drawingOnly) {
      report("OVERFLOW", j + 1, `"${after.slice(0, 24)}" runs past the right border`);
    }
  }
}

for (const file of files) {
  const rows = readFileSync(join(dir, file), "utf8").split("\n");
  let inFence = false;
  let lang = "";
  let block = [];
  let start = 0;

  const flush = () => {
    if (!block.length) return;
    blocks += 1;
    const report = (kind, ln, msg) => {
      problems += 1;
      console.log(`${kind.padEnd(8)} ${file}:${start + ln}  ${msg}`);
    };
    block.forEach((row, y) => {
      [...row].forEach((ch, x) => {
        if (ch === "┌") checkBox(block, x, y, report);
      });
    });
    block = [];
  };

  rows.forEach((row, i) => {
    const fence = /^\s*```(.*)$/.exec(row);
    if (fence) {
      if (!inFence) { inFence = true; lang = fence[1].trim(); start = i + 2; block = []; }
      else {
        inFence = false;
        if (["", "text", "ascii", "plaintext"].includes(lang)) flush();
        else block = [];
      }
      return;
    }
    if (inFence && ["", "text", "ascii", "plaintext"].includes(lang)) block.push(row);
  });
  if (inFence) {
    problems += 1;
    console.log(`FENCE    ${file}:${start}  this fence never closes`);
  }
}

console.log(`\n${files.length} documents · ${blocks} blocks · ${boxes} boxes · ${problems} problem(s)`);
process.exit(problems ? 1 : 0);
