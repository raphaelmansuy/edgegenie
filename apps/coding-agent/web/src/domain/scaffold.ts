/** The scaffold's step table, and the two rules that make it honest.
 *
 * A step is `done` only when a completed tool call returned that step's **proof field**. The model's
 * prose is never an input: this module reads what the app observed. That is the same principle as
 * `domain/evidence.verify`, applied to infrastructure (spec 013 [SCF-1], [P1]).
 *
 * Pure and total. The step definitions are in `seed/scaffold-steps.json`, which the Python twin
 * (`api/domain/scaffold.py`) also reads — one rule, two runtimes (spec 013 [07 §2.1]).
 */
import stepsJson from "./scaffold-steps.json";

export type StepState = "pending" | "running" | "done" | "blocked";

export interface StepDef {
  key: string;
  label: string;
  detail: string;
  tools: string[];
  proof: string;
  alt_proof?: string[];
  why: string;
}

export interface Call {
  name: string;
  status: string;
  callId?: string;
  /** The tool's reply text. JSON when it came from the server's `_trim`. */
  result?: string;
}

export interface Outcome {
  key: string;
  label: string;
  detail: string;
  state: StepState;
  proof: string;
  tool: string;
  reason: string;
}

export const STEPS: StepDef[] = (stepsJson as { steps: StepDef[] }).steps;

const fields = (result?: string): Record<string, unknown> => {
  if (!result) return {};
  try {
    const data = JSON.parse(result);
    return data && typeof data === "object" && !Array.isArray(data) ? (data as Record<string, unknown>) : {};
  } catch {
    return {};
  }
};

const nonEmpty = (v: unknown): boolean =>
  v !== undefined && v !== null && v !== "" && v !== 0 && !(Array.isArray(v) && v.length === 0)
  && !(typeof v === "object" && !Array.isArray(v) && Object.keys(v as object).length === 0);

/** The proof one call supplies for one step, or "" when it supplies none.
 *
 *  `{"ok": true}` is not a proof of a table; `{"ok": true, "row_count": 12}` is. That distinction is
 *  [E-9]: a completed status is not evidence, the proof field is. */
export function proved(step: StepDef, call: Call): string {
  if (call.status !== "completed" || !step.tools.includes(call.name)) return "";
  const data = fields(call.result);
  if (!data || data.error) return "";
  for (const field of [step.proof, ...(step.alt_proof ?? [])]) {
    const value = data[field];
    if (!nonEmpty(value)) continue;
    if (field === "rows") {
      const rows = data.rows;
      if (Array.isArray(rows) && Array.isArray(rows[0]) && rows[0].length) return String(rows[0][0]);
      continue;
    }
    if (field === "resources") {
      const names = (Array.isArray(value) ? value : [value]).map((r) =>
        typeof r === "object" && r !== null ? String((r as { name?: string }).name ?? "") : String(r));
      if (!names.includes("postgres")) return "";
      return "postgres";
    }
    if (field === "deploy_http_status" || field === "status") {
      const code = Number(value);
      return Number.isFinite(code) && code >= 200 && code < 300 ? String(code) : "";
    }
    return String(value).slice(0, 120);
  }
  return "";
}

/** One outcome per step, in order.
 *
 *  `O(c + s)`: the calls are grouped once, then each step reads its own group. A scoring loop per
 *  step per call would run on every streamed token — the mistake spec 012 found in the
 *  evidence-heading scan ([06 §6.4]).
 *
 *  Precedence, matching `api/domain/scaffold.py` exactly: `done` wins (a proof means it happened),
 *  and a `blocked` step makes every LATER step that has no proof `pending`, with the blocker named. */
export function compute(calls: Call[], steps: StepDef[] = STEPS): Outcome[] {
  const byName = new Map<string, Call[]>();
  for (const c of calls) {
    const list = byName.get(c.name);
    if (list) list.push(c); else byName.set(c.name, [c]);
  }
  const out: Outcome[] = [];
  let blocker = "";
  for (const step of steps) {
    const mine = step.tools.flatMap((t) => byName.get(t) ?? []);
    let proof = "";
    let tool = "";
    for (const c of mine) {
      const p = proved(step, c);
      if (p) { proof = p; tool = c.name; }      // the latest proof wins ([E-10])
    }
    let state: StepState;
    let reason = "";
    if (proof) {
      state = "done";
      if (blocker) reason = `ran after '${blocker}' was blocked`;
    } else if (blocker) {
      state = "pending";                        // the chain stopped earlier ([SCF-2], [E-8])
      reason = `not attempted: '${blocker}' is blocked`;
    } else if (mine.some((c) => c.status === "error")) {
      state = "blocked";
      blocker = step.key;
      const bad = mine.find((c) => c.status === "error");
      const data = fields(bad?.result);
      reason = String(data.error ?? data.platform_error ?? "the call failed");
    } else if (mine.some((c) => c.status === "running")) {
      state = "running";
    } else {
      state = "pending";
    }
    out.push({ key: step.key, label: step.label, detail: step.detail, state, proof, tool, reason });
  }
  return out;
}

/** `4 of 7 proven`, for a header. */
export function progress(outcomes: Outcome[]): { done: number; total: number } {
  return { done: outcomes.filter((o) => o.state === "done").length, total: outcomes.length };
}

/** The one step that needs attention, if any: a blocked one outranks a running one. */
export function focusStep(outcomes: Outcome[]): Outcome | null {
  return outcomes.find((o) => o.state === "blocked")
    ?? outcomes.find((o) => o.state === "running")
    ?? null;
}
