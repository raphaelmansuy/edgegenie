/** Check the simple ASCII screen grids, which the repository's Unicode box checker does not cover. */
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const dir = new URL('../../../../specs/010-tab-management/', import.meta.url);
let count = 0;
for (const file of readdirSync(dir).filter((name) => name.endsWith('.md'))) {
  const text = readFileSync(new URL(file, dir), 'utf8');
  for (const match of text.matchAll(/```ascii\n([\s\S]*?)```/g)) {
    const rows = match[1].trimEnd().split('\n'), width = rows[0].length;
    if (!/^\+-+\+$/.test(rows[0]) || rows.some((row) => row.length !== width || !/^(\+-+\+|\|.*\|)$/.test(row))) {
      throw new Error(`${fileURLToPath(new URL(file, dir))}: inconsistent wireframe grid`);
    }
    count++;
  }
}
if (count !== 4) throw new Error(`Expected four screen wireframes; found ${count}`);
console.log(`${count} ASCII screen wireframes: aligned borders and row widths`);
