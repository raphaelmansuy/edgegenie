/** The state vocabulary, held to the same table as the Python side.
 *
 *  `jobs-table.json` holds the cases; `api/domain/jobs.py` and `domain/jobs.ts` must both answer them
 *  identically. This file asserts half of that; `tests/test_jobs_domain.py` asserts the other. A word
 *  changed on one side alone fails one test that names the row — the mechanism `event-parity.json` and
 *  `scaffold-steps.json` already established for two other vocabularies.
 */
import { describe, expect, it } from "vitest";
import table from "./jobs-table.json";
import {
  asId, canCancel, canRepair, describeDuration, describeTasks, durationSeconds, isActive,
  isFailed, isPipelineId, isTerminal, pipelineWord, runActions, runWord, taskLevels, tone,
  updateIsActive, updateWord,
} from "./jobs";

interface RunRow {
  lifeCycle: string | null; result: string | null; word: string; tone: string;
  active: boolean; terminal: boolean; cancel: boolean; repair: boolean;
}
interface UpdateRow { state: string | null; word: string; active: boolean }
interface PipeRow { state: string | null; lastUpdate: string | null; word: string; why: string }

const RUNS = table.runs as RunRow[];
const UPDATES = table.updates as UpdateRow[];
const PIPELINES = table.pipelines as PipeRow[];

describe("the run table", () => {
  it.each(RUNS.map((r) => [r.lifeCycle, r.result, r] as const))(
    "%s + %s reads as the fixture says", (lifeCycle, result, row) => {
      expect(runWord(lifeCycle, result)).toBe(row.word);
      expect(tone(runWord(lifeCycle, result))).toBe(row.tone);
    });

  it.each(RUNS.map((r) => [r.lifeCycle, r] as const))(
    "%s agrees about active and terminal", (lifeCycle, row) => {
      expect(isActive(lifeCycle)).toBe(row.active);
      expect(isTerminal(lifeCycle)).toBe(row.terminal);
    });

  it.each(RUNS.map((r) => [r.lifeCycle, r.result, r] as const))(
    "%s + %s agrees about which controls exist", (lifeCycle, result, row) => {
      expect(canCancel(lifeCycle)).toBe(row.cancel);
      expect(canRepair(result, lifeCycle)).toBe(row.repair);
    });
});

describe("the update and pipeline tables", () => {
  it.each(UPDATES.map((r) => [r.state, r] as const))("%s reads as the fixture says", (state, row) => {
    expect(updateWord(state)).toBe(row.word);
    expect(updateIsActive(state)).toBe(row.active);
  });

  it.each(PIPELINES.map((r) => [r.state, r.lastUpdate, r] as const))(
    "%s + %s reads as the fixture says", (state, lastUpdate, row) => {
      expect(pipelineWord(state, lastUpdate)).toBe(row.word);
    });
});

describe("the field that is convenient is never the field that is honest", () => {
  it("a pipeline whose last update failed is not idle", () => {
    // THE row. `IDLE` is the pipeline's own state and it is true; the answer is the update's.
    expect(pipelineWord("IDLE", "FAILED")).toBe("failed");
    expect(pipelineWord("IDLE", "COMPLETED")).toBe("succeeded");
  });

  it("a terminated run is not a success", () => {
    expect(runWord("TERMINATED", "FAILED")).toBe("failed");
    expect(runWord("TERMINATED", "SUCCESS")).toBe("succeeded");
    expect(runWord("TERMINATED", null)).toBe("finished");
  });

  it("a running run has no result state and still reads running", () => {
    expect(runWord("RUNNING", null)).toBe("running");
  });

  it("an unknown word is never mapped to a synonym", () => {
    expect(runWord("TELEPORTING", null)).toBe("teleporting");
    expect(updateWord("MEDITATING")).toBe("meditating");
    expect(pipelineWord("FLYING", null)).toBe("flying");
  });

  it("nothing read is 'unknown', never 'ready'", () => {
    expect(runWord(null, null)).toBe("unknown");
    expect(pipelineWord(null, null)).toBe("unknown");
  });
});

describe("durations", () => {
  it.each([
    [1_000_000, 1_102_000, null, 102],
    [1_000_000, null, 1_012_000, 12],
    [null, null, 1_000_000, null],
    [null, 1_000_000, null, null],
    [1_000_000, 1_000_000, null, 0],
  ])("start %s end %s now %s is %s", (start, end, now, expected) => {
    expect(durationSeconds(start, end, now)).toBe(expected);
  });

  it("reads as a person says it, and a missing value is an em dash", () => {
    expect(describeDuration(null)).toBe("—");
    expect(describeDuration(38)).toBe("38 s");
    expect(describeDuration(102)).toBe("1 m 42 s");
    expect(describeDuration(3720)).toBe("1 h 02 m");
  });
});

describe("identity", () => {
  it("one id, however it is spelled", () => {
    expect(asId(812345678901)).toBe(812345678901);
    expect(asId("812345678901")).toBe(812345678901);
    expect(asId(" 812345678901 ")).toBe(812345678901);
  });

  it.each([0, -1, "abc", "", "12abc", null, undefined, 1.5])("refuses %s", (bad) => {
    expect(asId(bad)).toBeNull();
  });

  it("tells a pipeline id from a pipeline name", () => {
    expect(isPipelineId("f0e1c4a2-0000-11ee-be56-0242ac120002")).toBe(true);
    expect(isPipelineId("sales_medallion")).toBe(false);
    expect(isPipelineId("")).toBe(false);
  });
});

describe("the graph", () => {
  const t = (task_key: string, depends_on: string[] = []) => ({ task_key, depends_on });

  it("puts a chain one task per level", () => {
    expect(taskLevels([t("silver"), t("gold", ["silver"])])).toEqual([["silver"], ["gold"]]);
  });

  it("puts a fan-in's join below both parents", () => {
    // The assertion wireframe F2 makes: `join` is below `a` AND `b`, not beside one of them.
    const levels = taskLevels([t("a"), t("b"), t("join", ["a", "b"])]);
    expect(levels[levels.length - 1]).toEqual(["join"]);
    expect(new Set(levels[0])).toEqual(new Set(["a", "b"]));
  });

  it("puts a diamond's join after both branches", () => {
    expect(taskLevels([t("a"), t("b", ["a"]), t("c", ["a"]), t("d", ["b", "c"])]))
      .toEqual([["a"], ["b", "c"], ["d"]]);
  });

  it("leaves independent tasks in one level, in input order", () => {
    expect(taskLevels([t("zeta"), t("alpha"), t("mu")])).toEqual([["zeta", "alpha", "mu"]]);
  });

  it("draws nothing for a cycle", () => {
    // A partial picture of a cyclic job reads as a job that is merely small.
    expect(taskLevels([t("a", ["b"]), t("b", ["a"])])).toEqual([]);
  });

  it("does not crash on a dangling dependency", () => {
    // The validator reports it; the renderer must not also fail.
    expect(taskLevels([t("a", ["nope"])])).toEqual([["a"]]);
  });

  it("describes itself as a person would say it", () => {
    expect(describeTasks([t("a"), t("b", ["a"])])).toBe("2 tasks in 2 levels");
    expect(describeTasks([t("a"), t("b")])).toBe("2 tasks, all independent");
    expect(describeTasks([])).toBe("no tasks");
    expect(describeTasks([t("a", ["a"])])).toContain("cycle");
  });
});

describe("the control matrix", () => {
  it("offers Cancel while active and Repair after a failure, never both", () => {
    expect(runActions("RUNNING", null)).toEqual({ cancel: true, repair: false, runAgain: false });
    expect(runActions("TERMINATED", "FAILED")).toEqual({ cancel: false, repair: true, runAgain: true });
    expect(runActions("TERMINATED", "SUCCESS")).toEqual({ cancel: false, repair: false, runAgain: true });
    expect(runActions("BLOCKED", null)).toEqual({ cancel: true, repair: false, runAgain: false });
  });

  it("knows a success-with-failures is a failure", () => {
    expect(isFailed("SUCCESS_WITH_FAILURES")).toBe(true);
    expect(isFailed("SUCCESS")).toBe(false);
  });
});
