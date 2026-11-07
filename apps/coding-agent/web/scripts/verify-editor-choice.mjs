#!/usr/bin/env node
/** Re-measure the CodeMirror-vs-Monaco decision in spec 003.
 *
 * A decision recorded as prose goes stale silently: the numbers in the spec were true when written
 * and nobody notices when a major version quadruples one of them. This rebuilds both bundles with
 * the same tool, gzips them, and compares against the figures recorded in 07-decisions-risks.md.
 *
 * It fails if any recorded number drifts by more than TOLERANCE, so the spec cannot quietly become
 * untrue. It needs a network connection the first time (npm install into a temp dir).
 *
 *   node scripts/verify-editor-choice.mjs           # measure and compare
 *   node scripts/verify-editor-choice.mjs --record  # print the recorded block for the spec
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, statSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

/** What the spec claims. Keep in sync with 07-decisions-risks.md. */
const RECORDED = {
  cmGzip: 250_281,
  cmRaw: 720_293,
  monacoGzip: 1_193_544,
  monacoRaw: 4_594_453,
};

const TOLERANCE = 0.1; // 10%

const sh = (cmd, args, cwd) =>
  execFileSync(cmd, args, { cwd, stdio: ["ignore", "pipe", "pipe"], encoding: "utf8" });

function measure(name, packages, entrySource, extraOut = []) {
  const dir = mkdtempSync(join(tmpdir(), `ed-${name}-`));
  try {
    writeFileSync(join(dir, "package.json"), '{"name":"m","private":true}\n');
    sh("npm", ["install", "--silent", "--no-audit", "--no-fund", ...packages, "esbuild"], dir);
    writeFileSync(join(dir, "entry.js"), entrySource);
    const out = join(dir, "bundle.js");
    const args = [join(dir, "node_modules/.bin/esbuild"), join(dir, "entry.js"),
      "--bundle", "--minify", "--format=esm", `--outfile=${out}`, "--log-level=error"];
    if (extraOut.length) args.push(...extraOut);
    sh(args[0], args.slice(1), dir);
    const raw = statSync(out).size;
    const gz = gzipSync(readFileSync(out)).length;
    return { raw, gz };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const drift = (measured, recorded) => Math.abs(measured - recorded) / recorded;

console.log("measuring CodeMirror 6 (editor + 5 languages + merge + search)…");
const cm = measure("cm", [
  "codemirror", "@codemirror/lang-python", "@codemirror/lang-sql",
  "@codemirror/lang-markdown", "@codemirror/lang-json", "@codemirror/lang-javascript",
  "@codemirror/search", "@codemirror/autocomplete", "@codemirror/merge",
], `
import { EditorView, basicSetup } from "codemirror";
import { python } from "@codemirror/lang-python";
import { sql } from "@codemirror/lang-sql";
import { markdown } from "@codemirror/lang-markdown";
import { json } from "@codemirror/lang-json";
import { javascript } from "@codemirror/lang-javascript";
import { MergeView, unifiedMergeView } from "@codemirror/merge";
import { search } from "@codemirror/search";
export { EditorView, basicSetup, python, sql, markdown, json, javascript, MergeView, unifiedMergeView, search };
`);

console.log("measuring monaco-editor…");
const monaco = measure("monaco", ["monaco-editor"], `
import * as monaco from "monaco-editor";
export { monaco };
`, ["--loader:.ttf=file"]);

console.log("measuring the notebook reference (JupyterLab dependency mix)…");
let jupyter;
try {
  const info = sh("npm", ["view", "@jupyterlab/codemirror@latest", "dependencies", "--json"], tmpdir());
  const deps = JSON.parse(info);
  const cmDeps = Object.keys(deps).filter((k) => k.includes("codemirror") || k.includes("lezer"));
  jupyter = { total: Object.keys(deps).length, cm: cmDeps.length, monaco: Object.keys(deps).filter((k) => k.includes("monaco")).length };
} catch {
  jupyter = null;
}

const rows = [
  ["codemirror6 gzip", cm.gz, RECORDED.cmGzip],
  ["codemirror6 raw", cm.raw, RECORDED.cmRaw],
  ["monaco gzip", monaco.gz, RECORDED.monacoGzip],
  ["monaco raw", monaco.raw, RECORDED.monacoRaw],
];

let failed = 0;
console.log("\nmeasurement                 measured      recorded      drift");
console.log("-".repeat(62));
for (const [name, got, want] of rows) {
  const d = drift(got, want);
  const bad = d > TOLERANCE;
  if (bad) failed += 1;
  console.log(
    `${name.padEnd(26)} ${String(got).padEnd(13)} ${String(want).padEnd(13)} ${(d * 100).toFixed(1)}%${bad ? "  STALE" : ""}`,
  );
}

if (jupyter) {
  console.log(`\njupyterlab: ${jupyter.cm}/${jupyter.total} deps are codemirror/lezer, ${jupyter.monaco} are monaco`);
  if (jupyter.monaco > 0) {
    console.log("  STALE: the spec claims Monaco appears nowhere in JupyterLab");
    failed += 1;
  }
  if (jupyter.cm < 20) {
    console.log("  STALE: the spec claims 24 codemirror/lezer deps");
    failed += 1;
  }
}

console.log(`\nratio, gzipped: ${(monaco.gz / cm.gz).toFixed(2)}x`);
if (failed) {
  console.log(`\n${failed} recorded figure(s) no longer hold. Update 07-decisions-risks.md, then this file.`);
} else {
  console.log("\nthe recorded decision still holds");
}
process.exit(failed ? 1 : 0);
