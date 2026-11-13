/** Blob attachments: the client's courtesy copy of the server's rules.
 *
 * The server is the authority (spec 009 [D3]); everything here exists for one reason — a 12 MB file must
 * be refused in the same frame it is dropped, not after a round trip that uploads it to be rejected.
 *
 * The two implementations must never disagree about WORDS. `REFUSALS` below mirrors
 * `api/domain/blob.py::REFUSALS` key for key, and a test on each side asserts the key sets match. The
 * checks themselves are deliberately simple here: anything subtle belongs on the server, where it can be
 * enforced.
 */

export const MAX_BYTES = 8 * 1024 * 1024;
export const MAX_BYTES_TOTAL = 24 * 1024 * 1024;
export const MAX_ATTACHMENTS = 6;

/** The sentences. Server-side keys are the same; a test fails if one side gains a key the other lacks. */
export const REFUSALS = {
  too_big: "{name} is {size}; the limit is {limit}.",
  too_many: "At most {limit} attachments per message.",
  unknown_type: "{name} is not a file type this app can read.",
  mismatch: "{name} looks like {detected} but says it is {declared}.",
  empty: "{name} is empty.",
  bad_name: "{name} has characters a workspace path cannot hold.",
  no_vision: "Images need a model that can see them. {model} cannot; choose a vision model.",
  pdf_needs_eye: "A PDF has to be read as text or converted to an image first.",
  upload_failed: "{name} could not be uploaded: {reason}.",
  unavailable: "{name} is no longer available.",
} as const;

export type RefusalCode = keyof typeof REFUSALS;

/** The sentence for a code, with values filled in — the one formatter, so punctuation cannot drift. */
export function say(code: RefusalCode, values: Record<string, string | number> = {}): string {
  return REFUSALS[code].replace(/\{(\w+)\}/g, (_, k: string) => String(values[k] ?? `{${k}}`));
}

export interface Refusal {
  code: RefusalCode;
  message: string;
}

export type Family = "image" | "text" | "notebook" | "pdf" | "sheet" | "other";

/** What the app takes, generated from the same idea as the server's CAPABILITY table. */
export const ACCEPT = [
  "image/png", "image/jpeg", "image/webp", "image/gif",
  ".csv", ".tsv", ".md", ".txt", ".log", ".json", ".yaml", ".yml", ".py", ".sql", ".ipynb", ".pdf",
  ".xlsx", ".xls",
].join(",");

const IMAGE = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
const TEXTUAL = new Set([
  "application/json", "application/xml", "application/yaml", "application/javascript",
  "application/x-sh", "application/sql",
]);

/** Human sizes, matching the server's formatter so the two sentences agree. */
export function humanSize(n: number): string {
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} bytes`;
}

/** The family a File claims to be. Advisory — the server re-checks the bytes.
 *
 *  An unrecognised MIME type is NOT "text". A `.exe` whose type the OS did not report must be refused at
 *  the picker rather than uploaded to be refused by the server: guessing "text" for everything with a dot
 *  in its name offered every binary on the machine.
 */
export function familyOf(file: File): Family {
  const type = (file.type || "").toLowerCase();
  if (IMAGE.has(type)) return "image";
  if (type === "application/pdf" || /\.pdf$/i.test(file.name)) return "pdf";
  // A workbook. `[R-21]`: accepted here so the picker does not refuse it in the same frame it is dropped;
  // the server re-checks the BYTES, because a `.xlsx` is a ZIP and the name proves nothing.
  if (SHEET_EXT.test(file.name) || type === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      || type === "application/vnd.ms-excel") return "sheet";
  if (type.startsWith("text/") || TEXTUAL.has(type)) return "text";
  if (/\.ipynb$/i.test(file.name)) return "notebook";
  // No MIME reported by the OS. The extension is the only evidence left, and only a known text extension
  // counts — the server still verifies it decodes as UTF-8 before accepting it.
  if (TEXT_EXT.test(file.name)) return "text";
  return "other";
}

const TEXT_EXT = /\.(txt|md|csv|tsv|log|json|ya?ml|xml|html|css|jsx?|tsx?|py|sql|scala|r|sh|ini|toml|cfg)$/i;
/** A workbook. The server verifies the bytes; this is only what the picker accepts. */
const SHEET_EXT = /\.(xlsx|xls)$/i;

/** Sanitised name, mirroring the server: basename, safe characters, collapsed runs, kept extension. */
export function sanitiseName(name: string): string {
  const base = (name || "").replace(/\\/g, "/").split("/").pop() ?? "";
  let out = base
    .replace(/[^\w.\- ]/gu, "_")
    .replace(/_{2,}/g, "_")
    .replace(/ {2,}/g, " ")
    .replace(/^[.\s]+|[.\s]+$/g, "");
  if (!out || out === "." || out === "..") return "";
  if (out.length <= 120) return out;
  const dot = out.lastIndexOf(".");
  if (dot < 0) return out.slice(0, 120);
  const ext = out.slice(dot);
  return `${out.slice(0, Math.max(1, 120 - ext.length - 1))}${ext}`;
}

/** A pasted image is a Blob with no name; this gives it one that sorts sensibly and reads as what it is. */
export function pastedName(kind: string, at: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = `${at.getFullYear()}${pad(at.getMonth() + 1)}${pad(at.getDate())}-${pad(at.getHours())}${pad(at.getMinutes())}${pad(at.getSeconds())}`;
  return kind.startsWith("image/") ? `pasted-${stamp}.png` : `pasted-${stamp}`;
}

/** Why this file cannot be attached, or null when it can.
 *
 *  Deliberately shallow: size, emptiness, capability. Anything deeper is the server's call, because a
 *  browser cannot read magic bytes without loading the whole file twice.
 */
export function refuse(file: File, opts: { count: number; modelSeesImages: boolean; model?: string }): Refusal | null {
  const name = file.name || "the file";
  if (file.size > MAX_BYTES) {
    return { code: "too_big", message: say("too_big", { name, size: humanSize(file.size), limit: humanSize(MAX_BYTES) }) };
  }
  if (file.size === 0) return { code: "empty", message: say("empty", { name }) };
  if (opts.count >= MAX_ATTACHMENTS) {
    return { code: "too_many", message: say("too_many", { limit: MAX_ATTACHMENTS }) };
  }
  if (!sanitiseName(name)) return { code: "bad_name", message: say("bad_name", { name }) };
  const family = familyOf(file);
  if (family === "other") return { code: "unknown_type", message: say("unknown_type", { name }) };
  /* An image is NOT refused for want of a vision model. The bytes are the user's evidence, and refusing
     them leaves no way to hand a screenshot over at all — so it is accepted, and the chip says what the
     model will and will not get (spec 009 [P4], [D7]). `unseen` is the caller's hint for that label. */
  return null;
}
