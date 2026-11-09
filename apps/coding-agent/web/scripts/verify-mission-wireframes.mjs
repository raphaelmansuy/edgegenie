/** Verify the simple ASCII grids in spec 011; the shared checker handles Unicode diagrams. */
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const path = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../specs/011-ux-coding-mission/03-ux-ui.md');
const blocks = [...readFileSync(path, 'utf8').matchAll(/```ascii\n([\s\S]*?)```/g)];
assert.equal(blocks.length, 3);
for (const [index, block] of blocks.entries()) {
  const rows = block[1].trimEnd().split('\n');
  const columns = [...rows[0].matchAll(/\+/g)].map((m) => m.index);
  assert.equal(rows.at(-1), rows[0], `wireframe ${index + 1}: closing border`);
  for (const [line, row] of rows.entries()) {
    assert.equal(row.length, rows[0].length, `wireframe ${index + 1}, row ${line + 1}: width`);
    for (const col of columns) assert.ok(['|', '+'].includes(row[col]), `wireframe ${index + 1}, row ${line + 1}: border column ${col}`);
  }
}
console.log('3 ASCII wireframes: every row width and border column aligned');
