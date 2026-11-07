#!/usr/bin/env node
/** Verify every internal link and anchor in a spec set resolves.
 *
 * A spec set is read as a graph, and a dangling link is a broken promise to the reader. This walks
 * every .md file, extracts [text](target) and [text](file#anchor), and checks:
 *   - the file exists;
 *   - the file#anchor has a heading whose slug matches.
 *
 * Slugging follows GitHub: lowercase, spaces to hyphens, drop anything that is not alnum/hyphen/underscore.
 * Run:  node scripts/verify-spec-links.mjs <dir>
 */
import { readFileSync, readdirSync, existsSync, statSync } from "node:fs";
import { join, dirname, resolve, basename } from "node:path";

const dir = resolve(process.argv[2] ?? ".");
const files = readdirSync(dir).filter((f) => f.endsWith(".md")).sort();

const slug = (heading) =>
  heading
    .trim()
    .toLowerCase()
    // GitHub keeps letters/digits/space/hyphen, drops punctuation, and turns spaces into hyphens.
    .replace(/[`*_]/g, "")
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s+/g, "-");

/** headings outside fenced code blocks only: a `#` inside ``` is not a heading */
function anchorsOf(path) {
  const out = new Set();
  let fenced = false;
  for (const line of readFileSync(path, "utf8").split("\n")) {
    if (/^\s*```/.test(line)) { fenced = !fenced; continue; }
    if (fenced) continue;
    const m = /^(#{1,6})\s+(.*)$/.exec(line);
    if (m) out.add(slug(m[2]));
  }
  return out;
}

const cache = new Map();
const anchors = (p) => {
  if (!cache.has(p)) cache.set(p, anchorsOf(p));
  return cache.get(p);
};

let problems = 0;
let checked = 0;
for (const file of files) {
  const path = join(dir, file);
  const text = readFileSync(path, "utf8");
  // strip fenced blocks so a link inside example code is not checked
  const body = text.replace(/```[\s\S]*?```/g, "");
  for (const m of body.matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)) {
    const target = m[1];
    if (/^(https?:|mailto:)/.test(target)) continue;
    checked += 1;
    const [rel, anchor] = target.split("#");
    const targetPath = rel ? resolve(dirname(path), rel) : path;
    if (!existsSync(targetPath)) {
      console.log(`MISSING  ${file} -> ${target}`);
      problems += 1;
      continue;
    }
    if (anchor) {
      const real = rel ? targetPath : path;
      if (!anchors(real).has(anchor)) {
        console.log(`ANCHOR   ${file} -> ${target}`);
        console.log(`         ${basename(real)} has: ${[...anchors(real)].slice(0, 6).join(", ")}…`);
        problems += 1;
      }
    }
  }
}

console.log(`\n${files.length} documents, ${checked} internal links, ${problems} problem(s)`);
process.exit(problems ? 1 : 0);
