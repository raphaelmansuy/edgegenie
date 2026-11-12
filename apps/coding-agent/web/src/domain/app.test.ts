/** Databricks Apps as a page reads them: the health words, the resource, and the fix prompt.
 *
 * The health table is the point. Five states, and the one that matters is `starting`: a cold app is
 * healthy, and reporting it as `down` is the false alarm that teaches users to distrust the page
 * (spec 013 [AP-4], [E-14]).
 */
import {
  appStateWord, fixPrompt, healthSentence, logsUrl, postgresResource, tone, usingProject,
  type AppView,
} from "./app";

const app = (over: Partial<AppView> = {}): AppView => ({
  name: "tickets_app", url: "https://t-1.example", state: "running", stateRaw: "RUNNING",
  lakebase: "pg_tickets", resources: [], creator: "me@example.com", ...over,
});

describe("state words", () => {
  it.each([["RUNNING", "running"], ["STOPPED", "stopped"], ["CRASHED", "failing"],
    ["DEPLOYING", "deploying"], ["UNAVAILABLE", "starting"]])("%s reads as %s", (raw, word) => {
    expect(appStateWord(raw)).toBe(word);
  });

  it("gives each state a tone, so a page never invents a second vocabulary", () => {
    expect(tone("running")).toBe("good");
    expect(tone("starting")).toBe("busy");
    expect(tone("failing")).toBe("bad");
    expect(tone("stopped")).toBe("quiet");
  });
});

describe("the health sentence", () => {
  it("says what answered, and how fast", () => {
    expect(healthSentence({ status: 200, ms: 412, state: "running" }, "running"))
      .toBe("Answered 200 in 412 ms");
  });

  it("calls a cold start normal rather than broken", () => {
    // [E-14]
    const sentence = healthSentence({ status: null, ms: 15_000, state: "starting" }, "running");
    expect(sentence).toContain("Cold start");
    expect(sentence).toContain("normal");
  });

  it("distinguishes a 500 from a dead app", () => {
    // [E-13] the app is up and wrong, which is a different fix
    expect(healthSentence({ status: 500, ms: 300, state: "failing" }, "running"))
      .toBe("Answered 500 — the app is up and returning an error");
    expect(healthSentence({ status: null, ms: 10, state: "unreachable", detail: "ConnectError" }, "running"))
      .toContain("ConnectError");
  });

  it("admits when no check was taken", () => {
    expect(healthSentence(undefined, "running")).toContain("No health check");
  });
});

describe("the resource", () => {
  it("finds the postgres resource, whose absence is the F6 defect", () => {
    const withPg = app({ resources: [
      { name: "postgres", kind: "postgres", permission: "CAN_CONNECT_AND_CREATE", branch: "projects/p/branches/b" },
    ] });
    expect(postgresResource(withPg)?.permission).toBe("CAN_CONNECT_AND_CREATE");
    expect(postgresResource(app())).toBeNull();
  });

  it("narrows the app list to one project in one pass", () => {
    // [06 §6.2] one call, no fan-out
    const apps = [app(), app({ name: "orders", lakebase: "pg_orders" })];
    expect(usingProject(apps, "pg_tickets").map((a) => a.name)).toEqual(["tickets_app"]);
    expect(usingProject(apps, "")).toEqual([]);
  });
});

describe("links", () => {
  it("points at the logs, which are lost when compute stops", () => {
    expect(logsUrl("https://t-1.example/")).toBe("https://t-1.example/logz");
    expect(logsUrl("")).toBeNull();
  });
});

describe("the fix prompt", () => {
  it("carries the status code and the logs URL, so the agent need not rediscover them", () => {
    // [E-13]
    const prompt = fixPrompt(app({
      state: "failing",
      health: { status: 500, ms: 300, state: "failing" },
    }));
    expect(prompt).toContain("tickets_app");
    expect(prompt).toContain("HTTP 500");
    expect(prompt).toContain("https://t-1.example/logz");
    expect(prompt).toContain("prove it answers");
  });
});
