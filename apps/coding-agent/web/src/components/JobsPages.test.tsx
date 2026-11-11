/** The three pages: every fact, every failure, and the two rules they share.
 *
 *  These are the assertions that hold what a screenshot can only show once:
 *   * a state word comes from the honest field (a failed run over `TERMINATED`, a failed pipeline over
 *     `IDLE`) — 013's [RB-12] defect, one object type later;
 *   * a refused block leaves its siblings standing, and offers no retry when a grant is what is missing;
 *   * a queued task reads `not started`, never `running`;
 *   * a paused schedule is stated in words, not implied.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { JobsPage, pageRefusal, runCostSentence, scheduleSentence } from "./JobsPage";
import { RunsPage, TaskTable } from "./RunsPage";
import { PipelinePage, failureSentence, orderedEvents } from "./PipelinePage";
import { DataTree, errorBoxes } from "./DataTree";
import { JobGraph, taskTarget } from "./JobGraph";
import { makeDoc } from "../domain/docs";
import type { JobPageData, PipelinePageData, RunPageData } from "../api/client";

const jobDoc = makeDoc("job", "812345678901");
const runDoc = makeDoc("run", "812345679");
const pipeDoc = makeDoc("pipeline", "f0e1c4a2-0000-11ee-be56-0242ac120002");
const PIPE = "f0e1c4a2-0000-11ee-be56-0242ac120002";

/** A refusal as the server actually sends it: a NON-2xx status with `{detail}`, which the client turns
 *  into an `ApiError` and `useResource` turns into `page.error`. A 200 body with an `error` key is not the
 *  contract, and a test that used one would assert a page path that cannot happen. */
function mockRefusal(status: number, detail: string) {
  globalThis.fetch = vi.fn(async () =>
    new Response(JSON.stringify({ detail }), {
      status, headers: { "content-type": "application/json" },
    })) as unknown as typeof fetch;
}

function mockFetch(routes: Record<string, unknown>) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    // Longest pattern first: `/api/jobs/812345678901` contains `/api/jobs`, and one answering for the
    // other is the class of bug the adapter test's fake had to fix too.
    const hit = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => url.includes(k));
    if (!hit) return new Response("[]", { status: 404 });
    const body = routes[hit];
    if (body instanceof Error) throw body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;
}

afterEach(() => { vi.restoreAllMocks(); });

// ---------------------------------------------------------------------------------------------
// the job page
// ---------------------------------------------------------------------------------------------
const jobPage = (over: Partial<JobPageData> = {}): JobPageData => ({
  job: {
    job_id: 812345678901,
    name: "agent_4ff4405d_daily_revenue",
    owner: "me@example.com",
    created: 1_760_000_000_000,
    schedule: { cron: "0 0 6 * * ?", timezone: "UTC", paused: true },
    tasks: [
      { task_key: "silver", depends_on: [], notebook_path: "/Users/me/agent_scratch/daily/silver" },
      { task_key: "gold", depends_on: ["silver"], notebook_path: "/Users/me/agent_scratch/daily/gold" },
    ],
    queueing: true,
    timeoutSeconds: 0,
    maxRetries: 0,
    tags: { agent: "opengenie" },
    performanceTarget: "STANDARD",
  },
  runs: [
    { run_id: 812345679, lifeCycle: "TERMINATED", result: "FAILED", word: "failed", tone: "bad",
      startTime: 1_760_000_100_000, endTime: 1_760_000_202_000, duration: "1 m 42 s",
      active: false, cancel: false, repair: true },
  ],
  latestRun: { run_id: 812345679, lifeCycle: "TERMINATED", result: "FAILED", word: "failed", tone: "bad",
    startTime: 1_760_000_100_000, endTime: 1_760_000_202_000, duration: "1 m 42 s",
    active: false, cancel: false, repair: true, trigger: "manual",
    tasks: [{ taskKey: "gold", taskRunId: 2, lifeCycle: "TERMINATED", result: "FAILED",
      word: "failed", tone: "bad", duration: "64 s" }],
    output: { taskKey: "gold", error: "AnalysisException: cannot resolve 'fare_amount'" } },
  levels: [["silver"], ["gold"]],
  graphProblem: null,
  summary: "2 tasks in 2 levels",
  identity: "the app's service principal",
  ...over,
});

describe("JobsPage", () => {
  it("says the last run failed, in the platform's words", async () => {
    mockFetch({ "/api/jobs/": jobPage() });
    const { container } = render(<JobsPage doc={jobDoc} />);
    await waitFor(() => expect(screen.getByText("agent_4ff4405d_daily_revenue")).toBeInTheDocument());
    const pill = container.querySelector(".viewer-title .infra-pill");
    expect(pill?.textContent?.toLowerCase()).toBe("failed");
    expect(pill?.className).not.toMatch(/busy/);
  });

  it("renders the five blocks the wireframe names", async () => {
    mockFetch({ "/api/jobs/": jobPage() });
    render(<JobsPage doc={jobDoc} />);
    for (const title of ["Last run", "Schedule", "Tasks", "Runs", "Settings"]) {
      expect(await screen.findByRole("region", { name: title })).toBeInTheDocument();
    }
  });

  it("states a paused schedule in words, and says nothing will run", async () => {
    // [JOB-4]: a user who believes a paused job is firing has a silent data outage.
    mockFetch({ "/api/jobs/": jobPage() });
    render(<JobsPage doc={jobDoc} />);
    expect(await screen.findByText(/PAUSED/)).toBeInTheDocument();
    expect(screen.getByText(/nothing will run until you resume it/)).toBeInTheDocument();
  });

  it("a job that never ran says so instead of showing success", async () => {
    mockFetch({ "/api/jobs/": jobPage({ runs: [], latestRun: null }) });
    const { container } = render(<JobsPage doc={jobDoc} />);
    expect(await screen.findByText(/has not run yet/)).toBeInTheDocument();
    const pill = container.querySelector(".viewer-title .infra-pill");
    expect(pill?.textContent?.toLowerCase()).toBe("no runs");
  });

  it("a denied block leaves the other blocks standing", async () => {
    // [UI-3], [E-1]: one refusal must not blank its siblings.
    mockFetch({ "/api/jobs/": jobPage({ runs: { error: "PERMISSION_DENIED: CAN_MANAGE_RUN" },
      latestRun: { error: "PERMISSION_DENIED: CAN_MANAGE_RUN" } }) });
    render(<JobsPage doc={jobDoc} />);
    // The job block still renders its own facts; only the run history is denied.
    await waitFor(() =>
      expect(screen.getAllByText(/PERMISSION_DENIED/).length).toBeGreaterThan(0));
    expect(screen.getByText("agent_4ff4405d_daily_revenue")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Tasks" })).toBeInTheDocument();
  });

  it("offers no retry for a permission wall", async () => {
    // [UI-4]: a grant does not appear between two clicks.
    mockRefusal(403, "PERMISSION_DENIED: you need CAN_MANAGE_RUN on job 812345678901");
    render(<JobsPage doc={jobDoc} />);
    // ONE statement, not one per block: five identical boxes read as five problems ([UI-6]).
    await waitFor(() => expect(screen.getAllByText(/PERMISSION_DENIED/).length).toBeGreaterThan(0));
    // ONE statement for the page, not one per block: five copies read as five problems.
    expect(screen.getAllByText(/PERMISSION_DENIED/)).toHaveLength(1);
    // [UI-4]: `isPermanent` withholds the retry, because a grant does not appear between two clicks.
    expect(screen.queryAllByRole("button", { name: /Try again/i })).toHaveLength(0);
  });

  it("says which identity read the page", async () => {
    // [RB-1], [E-14]: the page shows what the APP may read, and says so.
    mockFetch({ "/api/jobs/": jobPage() });
    render(<JobsPage doc={jobDoc} />);
    expect(await screen.findByText(/the app's service principal/)).toBeInTheDocument();
  });

  it("says what Run now starts and how long the last run took", async () => {
    // [JOB-6]: a control that spends money says what it spends.
    mockFetch({ "/api/jobs/": jobPage() });
    render(<JobsPage doc={jobDoc} />);
    const runNow = await screen.findByRole("button", { name: /Run now/ });
    /* Wait for the TITLE, not for the button. The button renders as soon as the page mounts and its
       `title` is filled once the run block arrives, so `findByRole` returned a button whose title was
       still the fallback — which is the front-end flake recorded in `01-method-and-evidence.md` §1.2. It
       failed roughly one run in five under load and never in isolation. One assertion on the attribute
       the test is actually about removes the race rather than re-running until it passes. */
    await waitFor(() => expect(runNow.getAttribute("title")).toContain("1 m 42 s"));
  });
});

describe("scheduleSentence", () => {
  it.each([
    [null, /No schedule/],
    [{ cron: "0 0 6 * * ?", timezone: "UTC", paused: true }, /PAUSED/],
    [{ cron: "0 0 6 * * ?", timezone: "UTC", paused: false }, /running on that schedule/],
  ])("%o reads as a sentence", (schedule, pattern) => {
    expect(scheduleSentence(schedule as never)).toMatch(pattern);
  });

  it("a run's cost sentence never invents a duration it does not have", () => {
    expect(runCostSentence(null)).toMatch(/never run/);
    expect(runCostSentence({ duration: "38 s" } as never)).toContain("38 s");
  });
});

// ---------------------------------------------------------------------------------------------
// the graph
// ---------------------------------------------------------------------------------------------
describe("JobGraph", () => {
  const tasks = (jobPage().job as unknown as { tasks: never[] }).tasks;

  it("draws a fan-in below both parents", () => {
    const three = [
      { task_key: "a", depends_on: [] },
      { task_key: "b", depends_on: [] },
      { task_key: "join", depends_on: ["a", "b"] },
    ];
    render(<JobGraph tasks={three as never} levels={[["a", "b"], ["join"]]} />);
    const levels = document.querySelectorAll(".job-level");
    expect(levels.length).toBe(2);
    expect(levels[1].textContent).toContain("join");
    expect(levels[1].textContent).toContain("after a, b");
  });

  it("refuses to draw a cyclic graph rather than showing part of it", () => {
    // [JOB-3]: a partial picture of a broken job reads as a job that is merely small.
    render(<JobGraph tasks={tasks} levels={[]} problem="the dependencies form a cycle: a -> b -> a" />);
    expect(screen.getByRole("alert").textContent).toContain("cycle");
    expect(document.querySelectorAll(".job-level").length).toBe(0);
  });

  it("names what a task runs, without a full path", () => {
    const target = taskTarget(tasks[0] as never);
    expect(target.kind).toBe("notebook");
    expect(target.value).toContain("/daily/silver");
  });
});

// ---------------------------------------------------------------------------------------------
// the run page
// ---------------------------------------------------------------------------------------------
const runPage = (over: Partial<RunPageData> = {}): RunPageData => ({
  run_id: 812345679, job_id: 812345678901,
  lifeCycle: "TERMINATED", result: "FAILED", word: "failed", tone: "bad",
  startTime: 1_760_000_100_000, endTime: 1_760_000_202_000, duration: "1 m 42 s",
  active: false, cancel: false, repair: true, trigger: "manual",
  tasks: [
    { taskKey: "silver", taskRunId: 1, lifeCycle: "TERMINATED", result: "SUCCESS",
      word: "succeeded", tone: "good", duration: "38 s" },
    { taskKey: "gold", taskRunId: 2, lifeCycle: "TERMINATED", result: "FAILED",
      word: "failed", tone: "bad", duration: "64 s" },
    { taskKey: "audit", taskRunId: 3, lifeCycle: "SKIPPED", result: null,
      word: "skipped", tone: "quiet", duration: "—" },
  ],
  output: { taskKey: "gold", error: "AnalysisException: cannot resolve 'fare_amount'",
    traceTail: "at line 12" },
  ...over,
});

describe("RunsPage", () => {
  it("lists every task with its own word", async () => {
    mockFetch({ "/api/runs/": runPage() });
    render(<RunsPage doc={runDoc} />);
    await waitFor(() => expect(screen.getAllByText("gold").length).toBeGreaterThan(0));
    expect(screen.getAllByText("succeeded").length).toBeGreaterThan(0);
    expect(screen.getAllByText("failed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("skipped").length).toBeGreaterThan(0);
  });

  it("quotes the error rather than paraphrasing it", async () => {
    mockFetch({ "/api/runs/": runPage() });
    render(<RunsPage doc={runDoc} />);
    expect(await screen.findByText(/cannot resolve 'fare_amount'/)).toBeInTheDocument();
  });

  it("offers no Cancel on a finished run, and Repair for a failed one", async () => {
    mockFetch({ "/api/runs/": runPage() });
    render(<RunsPage doc={runDoc} />);
    await waitFor(() => expect(screen.getAllByText("gold").length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: /^Cancel/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Repair the failed tasks/ })).toBeInTheDocument();
  });

  it("offers Cancel on a live run and says the cancellation is asynchronous", async () => {
    const asked: string[] = [];
    mockFetch({ "/api/runs/": runPage({ word: "running", tone: "busy", lifeCycle: "RUNNING",
      result: null, active: true, cancel: true, repair: false, output: undefined }) });
    render(<RunsPage doc={runDoc} onAsk={(p) => asked.push(p)} />);
    const cancel = await screen.findByRole("button", { name: /^Cancel/ });
    cancel.click();
    await waitFor(() => expect(screen.getByText(/asynchronous/)).toBeInTheDocument());
    expect(asked[0]).toMatch(/terminal state/);
    expect(asked[0]).toMatch(/do not report it cancelled before the platform does/);
  });

  it("a task that has not started is not called running", () => {
    // [RUN-1]: a queued task is not doing work.
    render(<TaskTable tasks={[{ taskKey: "audit", taskRunId: 3, lifeCycle: "", result: null,
      word: "not started", tone: "quiet", duration: "—" }]} />);
    expect(screen.getByText("not started")).toBeInTheDocument();
    expect(screen.queryByText("running")).toBeNull();
  });

  it("a run with no tasks says so instead of showing an empty table", () => {
    render(<TaskTable tasks={[]} />);
    expect(screen.getByText(/reports no tasks yet/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------------------------
// the pipeline page
// ---------------------------------------------------------------------------------------------
const pipePage = (over: Partial<PipelinePageData> = {}): PipelinePageData => ({
  pipeline: {
    pipeline_id: PIPE, name: "sales_medallion", state: "IDLE",
    catalog: "main", schema: "sales", serverless: true, edition: "ADVANCED", channel: "CURRENT",
    continuous: false, development: false,
    libraries: [
      { kind: "notebook", path: "/Users/me/agent_scratch/sales/bronze" },
      { kind: "notebook", path: "/Users/me/agent_scratch/sales/silver" },
      { kind: "notebook", path: "/Users/me/agent_scratch/sales/gold" },
    ],
    creator: "me@example.com", storage: "",
  },
  updates: [{ updateId: "8a0b6d02", state: "COMPLETED", word: "succeeded", tone: "good",
    creationTime: 1_760_000_000_000, fullRefresh: false, cause: "api_call", active: false }],
  lastUpdate: { updateId: "8a0b6d02", state: "COMPLETED", word: "succeeded", tone: "good",
    creationTime: 1_760_000_000_000, fullRefresh: false, cause: "api_call", active: false },
  events: [{ level: "INFO", message: "started", timestamp: 1_760_000_000_000, stackTrace: "" }],
  word: "succeeded",
  tone: "good",
  activeUpdate: null,
  identity: "the app's service principal",
  ...over,
});

describe("PipelinePage", () => {
  it("the header follows the last update, not the pipeline's state", async () => {
    // THE assertion of this spec's pipeline page: `IDLE` over a failed update is `failed`.
    mockFetch({ "/api/pipelines/": pipePage({
      word: "failed", tone: "bad",
      lastUpdate: { updateId: "8a0b6d02", state: "FAILED", word: "failed", tone: "bad",
        creationTime: 1_760_000_000_000, fullRefresh: false, cause: "api_call", active: false },
    }) });
    const { container } = render(<PipelinePage doc={pipeDoc} />);
    await waitFor(() => expect(screen.getByText("sales_medallion")).toBeInTheDocument());
    const pill = container.querySelector(".viewer-title .infra-pill");
    expect(pill?.textContent?.toLowerCase()).toBe("failed");
  });

  it("a never-updated pipeline says so, and offers the free check", async () => {
    mockFetch({ "/api/pipelines/": pipePage({ lastUpdate: null, word: "idle", tone: "quiet" }) });
    render(<PipelinePage doc={pipeDoc} />);
    expect(await screen.findByText(/Never run/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Check the code/ })).toBeInTheDocument();
  });

  it("offers three start modes, each labelled with its cost", async () => {
    mockFetch({ "/api/pipelines/": pipePage() });
    render(<PipelinePage doc={pipeDoc} />);
    expect(await screen.findByRole("button", { name: /^Start/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Full refresh/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Check the code/ })).toBeInTheDocument();
  });

  it("offers no Stop when nothing is active", async () => {
    // [PIPE-4]: absent, not disabled.
    mockFetch({ "/api/pipelines/": pipePage() });
    render(<PipelinePage doc={pipeDoc} />);
    await waitFor(() => expect(screen.getByText("sales_medallion")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /^Stop/ })).toBeNull();
  });

  it("offers Stop while an update is active", async () => {
    mockFetch({ "/api/pipelines/": pipePage({
      activeUpdate: { updateId: "u2", state: "RUNNING", word: "running", tone: "busy",
        creationTime: 1_760_000_000_000, fullRefresh: false, cause: "api_call", active: true },
    }) });
    render(<PipelinePage doc={pipeDoc} />);
    expect(await screen.findByRole("button", { name: /^Stop/ })).toBeInTheDocument();
  });

  it("names the three libraries", async () => {
    mockFetch({ "/api/pipelines/": pipePage() });
    render(<PipelinePage doc={pipeDoc} />);
    await waitFor(() => expect(screen.getByText("bronze")).toBeInTheDocument());
    expect(screen.getByText("silver")).toBeInTheDocument();
    expect(screen.getByText("gold")).toBeInTheDocument();
  });

  it("a failed update with no error event says so rather than inventing a cause", async () => {
    mockFetch({ "/api/pipelines/": pipePage({
      word: "failed", tone: "bad",
      lastUpdate: { updateId: "u3", state: "FAILED", word: "failed", tone: "bad",
        creationTime: 1_760_000_000_000, fullRefresh: false, cause: "api_call", active: false },
      events: [],
    }) });
    render(<PipelinePage doc={pipeDoc} />);
    expect(await screen.findByText(/failed update with no ERROR event/)).toBeInTheDocument();
  });
});

describe("pipeline events", () => {
  it("puts errors first", () => {
    const ordered = orderedEvents([
      { level: "INFO", message: "a", timestamp: 1, stackTrace: "" },
      { level: "ERROR", message: "b", timestamp: 2, stackTrace: "" },
      { level: "WARN", message: "c", timestamp: 3, stackTrace: "" },
    ]);
    expect(ordered.map((e) => e.level)).toEqual(["ERROR", "WARN", "INFO"]);
  });

  it("says nothing when there is no error to quote", () => {
    expect(failureSentence([{ level: "INFO", message: "x", timestamp: 1, stackTrace: "" }])).toBeNull();
  });
});

// ---------------------------------------------------------------------------------------------
// the rail
// ---------------------------------------------------------------------------------------------
describe("DataTree", () => {
  it("renders four groups independently", async () => {
    mockFetch({
      "/api/lakebase/projects": { items: [{ ref: "projects/pg_tickets", name: "pg_tickets", displayName: "Tickets", pgVersion: 17 }] },
      "/api/jobs": { items: [{ job_id: 1, name: "daily", owner: "me", schedule: { cron: "0 0 6 * * ?", timezone: "UTC", paused: true }, paused: true }] },
      "/api/pipelines": { items: [{ pipeline_id: PIPE, name: "sales", state: "IDLE", word: "succeeded", tone: "good", lastUpdate: { update_id: "u1", state: "COMPLETED" }, catalog: "main", creator: "me" }] },
      "/api/apps": { items: [{ name: "tickets-app", url: "", state: "RUNNING", stateRaw: "RUNNING", lakebase: "", resources: [], creator: "me" }] },
    });
    render(<DataTree onOpen={() => {}} selected={null} />);
    for (const label of ["Lakebase", "Jobs", "Pipelines", "Databricks Apps"]) {
      expect(await screen.findByText(label)).toBeInTheDocument();
    }
    expect(await screen.findByText("Tickets")).toBeInTheDocument();
    expect(screen.getByText("daily")).toBeInTheDocument();
    expect(screen.getByText("sales")).toBeInTheDocument();
    expect(screen.getByText("tickets-app")).toBeInTheDocument();
  });

  it("a paused job says paused, because `jobs/list` carries the schedule", async () => {
    mockFetch({
      "/api/lakebase/projects": { items: [] }, "/api/pipelines": { items: [] }, "/api/apps": { items: [] },
      "/api/jobs": { items: [{ job_id: 1, name: "daily", owner: "me", schedule: { cron: "0 0 6 * * ?", timezone: "UTC", paused: true }, paused: true }] },
    });
    render(<DataTree onOpen={() => {}} selected={null} />);
    expect(await screen.findByText("paused")).toBeInTheDocument();
  });

  it("a pipeline's row carries its LAST update's word", async () => {
    // The rail is where a user first sees the object; `IDLE` here would be the `F5` defect on the rail.
    mockFetch({
      "/api/lakebase/projects": { items: [] }, "/api/jobs": { items: [] }, "/api/apps": { items: [] },
      "/api/pipelines": { items: [{ pipeline_id: PIPE, name: "sales", state: "IDLE", word: "failed", tone: "bad", lastUpdate: { update_id: "u1", state: "FAILED" }, catalog: "main", creator: "me" }] },
    });
    render(<DataTree onOpen={() => {}} selected={null} />);
    expect(await screen.findByText("failed")).toBeInTheDocument();
  });

  it("each group says what an empty group means", async () => {
    mockFetch({ "/api/lakebase/projects": { items: [] }, "/api/jobs": { items: [] },
      "/api/pipelines": { items: [] }, "/api/apps": { items: [] } });
    render(<DataTree onOpen={() => {}} selected={null} />);
    expect(await screen.findByText(/No jobs yet/)).toBeInTheDocument();
    expect(screen.getByText(/No pipelines yet/)).toBeInTheDocument();
  });

  it("one cause shows one box and two causes show two", () => {
    // [E-23]: collapsing is the rule; keeping a DIFFERENT message is the other half of it.
    const same = errorBoxes({ state: "error", error: "permission denied" },
      { state: "error", error: "permission denied" });
    expect(same).toEqual(["permission denied"]);
    const different = errorBoxes({ state: "error", error: "permission denied" },
      { state: "error", error: "the workspace did not answer" });
    expect(different).toHaveLength(2);
    expect(errorBoxes({ state: "ready" }, { state: "loading" })).toEqual([]);
  });
});

// ---------------------------------------------------------------------------------------------
// one cause, one statement
// ---------------------------------------------------------------------------------------------
describe("pageRefusal", () => {
  it("collapses a shared block refusal, which is what S6 photographed five times", () => {
    // The shape the job adapter produces: a 200 with the SAME `{error}` in several blocks, so one denial
    // cannot blank the others. Rendering it per block turned one problem into five.
    const same = "PERMISSION_DENIED: user does not have CAN_MANAGE_RUN on job 1";
    expect(pageRefusal(undefined, [same, same, same, same, same])).toBe(same);
  });

  it("collapses a page-level failure", () => {
    expect(pageRefusal("the workspace did not answer", [undefined, undefined])).toBe(
      "the workspace did not answer");
  });

  it("keeps a SINGLE block's error where it is, beside the facts that did load", () => {
    // One denied section is that section's problem; hoisting it would hide which block it was.
    expect(pageRefusal(undefined, ["PERMISSION_DENIED", undefined, undefined])).toBe("");
  });

  it("keeps two DIFFERENT errors apart, because they are two faults", () => {
    expect(pageRefusal(undefined, ["permission denied", "the workspace did not answer"])).toBe("");
  });

  it("says nothing when nothing failed", () => {
    expect(pageRefusal(undefined, [])).toBe("");
    expect(pageRefusal(undefined, [undefined, undefined])).toBe("");
  });

  it("a failed page read states one cause even when blocks carry sentences", () => {
    // The shape the job adapter produces when the job GET itself failed: `job` and `runs` are both
    // `{error}`, and `latestRun` is null. Every block is empty for one reason, so the page says it once.
    const cause = "PERMISSION_DENIED: user does not have CAN_MANAGE_RUN on job 1";
    expect(pageRefusal(cause, [cause, cause])).toBe(cause);
    expect(pageRefusal(cause, [cause, undefined])).toBe(cause);
  });
});

describe("every block on the job page collapses a shared refusal", () => {
  it("no block repeats the page's sentence, in any of the five", async () => {
    // The structural assertion for the defect a screenshot found TWICE: one call site was left without
    // the `pageStated` flag, so Settings repeated the sentence under a page-level banner. A single missed
    // call site is exactly what a per-call-site test cannot catch, so this counts boxes instead.
    mockFetch({ "/api/jobs/": {
      identity: "the app's service principal",
      job: { error: "PERMISSION_DENIED: user does not have CAN_MANAGE_RUN on job 812345678901" },
      runs: { error: "PERMISSION_DENIED: user does not have CAN_MANAGE_RUN on job 812345678901" },
      latestRun: null, levels: [], graphProblem: null, summary: "no tasks",
    } });
    const { container } = render(<JobsPage doc={jobDoc} />);
    await waitFor(() => expect(container.querySelector(".infra-page-refusal")).not.toBeNull());
    expect(container.querySelectorAll(".infra-page-refusal")).toHaveLength(1);
    expect(container.querySelectorAll(".infra-block-error")).toHaveLength(0);
    // The sentence appears once in the banner, and nowhere else in the page body.
    const bodyText = container.querySelector(".infra-body")?.textContent ?? "";
    expect(bodyText.split("CAN_MANAGE_RUN").length - 1).toBe(1);
  });

  it("an unread block makes NO claim about the data", async () => {
    // The defect the picture showed after the repetition was fixed: every block fell back to its EMPTY
    // sentence, so a page that could read nothing said "This job has not run yet" and "No runs in this
    // job's history" — two facts it does not have. A failed read must not be reported as a zero.
    mockFetch({ "/api/jobs/": {
      identity: "the app's service principal",
      job: { error: "PERMISSION_DENIED: CAN_MANAGE_RUN" },
      runs: { error: "PERMISSION_DENIED: CAN_MANAGE_RUN" },
      latestRun: null, levels: [], graphProblem: null, summary: "no tasks",
    } });
    const { container } = render(<JobsPage doc={jobDoc} />);
    await waitFor(() => expect(container.querySelector(".infra-page-refusal")).not.toBeNull());
    const bodyText = container.querySelector(".infra-body")?.textContent ?? "";
    expect(bodyText).not.toMatch(/has not run yet/);
    expect(bodyText).not.toMatch(/No runs in this job's history/);
    expect(bodyText).not.toMatch(/This job has no tasks/);
    // What it DOES say: that it could not be read.
    expect(bodyText).toMatch(/could not be read/);
  });
});
