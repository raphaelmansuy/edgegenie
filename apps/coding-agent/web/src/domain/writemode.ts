/** The write-mode vocabulary, mirrored from `api/domain/write_mode.py`. Pure. `[R-9]`.
 *
 *  The server is the authority; this is the client's copy so the picker, the header and the fence hint
 *  cannot describe the same mode three ways. `paging.ts` and `blob.ts` follow the same pattern, and each
 *  is held to a test on both sides.
 */

export type WriteModeId = "read-only" | "fenced" | "ask";

export interface WriteMode {
  id: WriteModeId;
  label: string;
  /** One sentence, the same sentence the server sends. */
  sentence: string;
  /** Whether any change may happen at all. `read-only` never does. */
  mutates: boolean;
}

export const WRITE_MODES: readonly WriteMode[] = [
  {
    id: "read-only",
    label: "Read only",
    sentence: "The agent may read. Every change is refused.",
    mutates: false,
  },
  {
    id: "fenced",
    label: "Fenced",
    sentence: "The agent may change things inside your folder and schema. Anything else asks you first.",
    mutates: true,
  },
  {
    id: "ask",
    label: "Ask me",
    sentence: "Every change waits for your approval.",
    mutates: true,
  },
] as const;

export const DEFAULT_WRITE_MODE: WriteModeId = "fenced";

/** A mode from anything the server may send. Unknown text is the DEFAULT, never a wider mode. */
export function asWriteMode(value: string | null | undefined): WriteModeId {
  const found = WRITE_MODES.find((m) => m.id === value);
  return found ? found.id : DEFAULT_WRITE_MODE;
}

export function writeMode(id: string | null | undefined): WriteMode {
  const key = asWriteMode(id);
  return WRITE_MODES.find((m) => m.id === key)!;
}

/** The chip the header shows. A read-only session must be visible at a glance: it is the mode in which
 *  a plausible request will be refused, and a user should not have to try in order to find out. */
export function writeModeChip(id: string | null | undefined): { label: string; tone: "quiet" | "warn" } {
  const mode = writeMode(id);
  return { label: mode.label, tone: mode.mutates ? "quiet" : "warn" };
}

/** What the composer hint says, so a user knows before typing why a change may be refused. */
export function writeModeHint(id: string | null | undefined): string {
  const mode = writeMode(id);
  if (mode.id === "read-only") return "Read only: the agent cannot change anything here.";
  if (mode.id === "ask") return "Every change will wait for your approval.";
  return "";
}
