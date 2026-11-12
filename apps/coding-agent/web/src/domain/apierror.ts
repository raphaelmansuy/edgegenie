/** What an error response says, as one sentence a person can read. Pure.
 *
 * The server answers in three shapes: a plain `detail` string (our own refusals, already written for
 * people), `{detail: {detail, field}}` (a credential form), and FastAPI's validation list
 * (`[{loc: ["body", "folder"], msg: "String should have at least 1 character"}]`). The last one used to
 * reach the screen as raw JSON; it is turned into "folder: String should have at least 1 character".
 */
export function errorText(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      const e = d as { loc?: unknown[]; msg?: string };
      const field = (e.loc ?? []).filter((x) => x !== "body" && x !== "query").join(".");
      return `${field ? `${field}: ` : ""}${e.msg ?? "is not valid"}`;
    });
    if (parts.length) return parts.join("; ");
  }
  const nested = (detail as { detail?: unknown } | undefined)?.detail;
  if (typeof nested === "string" && nested.trim()) return nested;
  const message = (detail as { message?: unknown } | undefined)?.message;
  if (typeof message === "string" && message.trim()) return message;
  return fallback;
}
