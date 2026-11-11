import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

/** The version, read from the file that ships inside the deployment.
 *
 *  Not from `package.json` and not from a git tag: `apps/coding-agent/VERSION` is the one file the
 *  API, this build and `scripts/verify-deployed.sh` all read, so a bundle cannot claim a version the
 *  server does not answer with. A missing or malformed file is stated as `unknown` rather than
 *  silently becoming `0.0.0`. */
function appVersion(): string {
  try {
    const text = readFileSync(resolve(here, "..", "VERSION"), "utf8").trim();
    return /^\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$/.test(text) ? text : "unknown";
  } catch {
    return "unknown";
  }
}

/** The commit, when a checkout says so.
 *
 *  Empty in the `prod` transport, which deploys from a Workspace folder with no `.git`. Empty is the
 *  honest answer there; inventing a hash would name a revision the container does not contain. */
function appCommit(): string {
  if (process.env.APP_GIT_COMMIT) return process.env.APP_GIT_COMMIT.trim();
  try {
    return execFileSync("git", ["rev-parse", "--short=7", "HEAD"], { cwd: here, encoding: "utf8" }).trim();
  } catch {
    return "";
  }
}

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", sourcemap: false },
  // Compile-time facts, so the page states its own version without a request: the footer is right
  // even if `/api/version` is unreachable, and the two are compared by the deployment verifier.
  define: {
    __APP_VERSION__: JSON.stringify(appVersion()),
    __APP_COMMIT__: JSON.stringify(appCommit()),
    __APP_BUILT__: JSON.stringify(new Date().toISOString()),
  },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"] },
});
