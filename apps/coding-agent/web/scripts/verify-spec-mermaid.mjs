/** Parse every mermaid block in a spec set with the real Mermaid parser.
 *  A diagram that does not parse renders as a red error box in the docs, which is worse than no diagram.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
/* Needs mermaid + jsdom. Install them where this script can resolve them:
     cd /tmp && mkdir mmd && cd mmd && npm i mermaid jsdom
     NODE_PATH=/tmp/mmd/node_modules node verify-spec-mermaid.mjs <dir>
   They are not app dependencies: a spec check must not ship in the bundle. */
const { JSDOM } = await import(process.env.JSDOM_PATH ?? "jsdom");

const dir = process.argv[2];
if (!dir) throw new Error("usage: node verify-spec-mermaid.mjs <dir>");

const dom = new JSDOM("<!doctype html><html><body></body></html>");
globalThis.window = dom.window;
globalThis.document = dom.window.document;

const mermaid = (await import(process.env.MERMAID_PATH ?? "mermaid")).default;
mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });

let total = 0;
let bad = 0;
for (const f of readdirSync(dir).filter((x) => x.endsWith(".md")).sort()) {
  const text = readFileSync(join(dir, f), "utf8");
  const blocks = [...text.matchAll(/```mermaid\n([\s\S]*?)```/g)].map((m) => m[1]);
  for (let i = 0; i < blocks.length; i += 1) {
    total += 1;
    const src = blocks[i].trim();
    const kind = src.split("\n")[0].trim();
    try {
      await mermaid.parse(src);
      console.log(`  ok    ${f} #${i + 1} (${kind})`);
    } catch (e) {
      bad += 1;
      const msg = String(e?.message ?? e).split("\n").slice(0, 4).join(" | ");
      console.log(`  FAIL  ${f} #${i + 1} (${kind})\n        ${msg}`);
    }
  }
}
console.log(`\n${total} diagrams, ${bad} failing to parse`);
process.exit(bad ? 1 : 0);
