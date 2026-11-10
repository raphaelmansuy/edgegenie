/** The project and app pages: every fact, every failure, and the one rule they share —
 *  a value that could not be read says so instead of rendering as zero (spec 013 [UI-3], [E-11]). */
import { render, screen, waitFor } from "@testing-library/react";
import { LakebasePage } from "./LakebasePage";
import { AppPage } from "./AppPage";
import { makeDoc } from "../domain/docs";

const project = makeDoc("lakebase", "projects/pg_tickets", "pg_tickets");
const app = makeDoc("app", "tickets_app");

const page = (over: Record<string, unknown> = {}) => ({
  // [RB-12] This fixture must match what the API ACTUALLY sends: a project has no `state` and no
  // `ready`. The old fixture invented both, which is why every test passed while the header pill read
  // `project.state`, got `undefined`, and said "loading" forever over a ready project.
  project: { ref: "projects/pg_tickets", name: "pg_tickets", displayName: "Tickets",
    pgVersion: 17, defaultBranch: "production" },
  branches: [{ ref: "projects/pg_tickets/branches/production", name: "production", isDefault: true, state: "ready" },
    { ref: "projects/pg_tickets/branches/agent-4ff", name: "agent-4ff", isDefault: false, state: "ready" }],
  databases: [{ ref: "projects/pg_tickets/branches/production/databases/databricks_postgres",
    name: "databricks_postgres" }],
  compute: [{ ref: "projects/pg_tickets/branches/production/endpoints/primary", name: "primary",
    type: "ENDPOINT_TYPE_READ_WRITE", state: "ready", suspended: false,
    host: "ep-cool.example", range: "0.5 – 4 CU   max − min = 3.5  ✓ (≤ 16)", rangeValid: true }],
  ...over,
});

function mockFetch(routes: Record<string, unknown>) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const hit = Object.keys(routes).find((k) => url.includes(k));
    if (!hit) return new Response("[]", { status: 404 });
    const body = routes[hit];
    if (body instanceof Error) throw body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }) as unknown as typeof fetch;
}

afterEach(() => { vi.restoreAllMocks(); });

describe("LakebasePage", () => {
  it("shows every fact a user needs, each from a call", async () => {
    // [UI-3]
    mockFetch({
      "/tables": { schema: "public", tables: ["tickets", "agents"], truncated: false },
      "/api/lakebase/projects/": page(),
    });
    render(<LakebasePage doc={project} workspace={{ host: "https://h.cloud.databricks.com" }} />);
    await waitFor(() => expect(screen.getByText("Tickets")).toBeInTheDocument());
    expect(screen.getByText("17")).toBeInTheDocument();               // pg version
    expect(screen.getByText("production", { selector: ".infra-mono" })).toBeInTheDocument();
    expect(screen.getByText("ep-cool.example")).toBeInTheDocument();
    expect(screen.getByText(/max − min = 3.5/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("tickets")).toBeInTheDocument());
  });

  it("renders the six blocks the wireframe names", async () => {
    mockFetch({ "/tables": { schema: "public", tables: [], truncated: false }, "/api/lakebase/projects/": page() });
    render(<LakebasePage doc={project} workspace={null} />);
    for (const title of ["Project", "Compute", "Branches", "Databases"]) {
      expect(await screen.findByRole("region", { name: title })).toBeInTheDocument();
    }
  });

  it("says a value could not be read rather than showing zero", async () => {
    // [E-11] the rule this page exists to keep
    mockFetch({ "/tables": { schema: "public", tables: [], truncated: false },
      "/api/lakebase/projects/": page({ project: { ref: "projects/p", name: "p", displayName: "P" } }) });
    render(<LakebasePage doc={project} workspace={null} />);
    await waitFor(() => expect(screen.getByText("P")).toBeInTheDocument());
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("derives 'ready' in the header instead of saying 'loading' forever", async () => {
    // [RB-12] The defect a SCREENSHOT found. The project payload has no `state`, so a header that read
    // one rendered `loading` over a project whose branch said READY. The old fixture invented
    // `state: "ready"` on the project, so no test could see it. This test refuses the invention.
    mockFetch({ "/tables": { schema: "public", tables: [], truncated: false },
      "/api/lakebase/projects/": page() });
    const { container } = render(<LakebasePage doc={project} workspace={null} />);
    await waitFor(() => expect(screen.getByText("Tickets")).toBeInTheDocument());
    // Wait for the branch read, which is what makes readiness knowable.
    await waitFor(() => {
      const pill = container.querySelector(".viewer-title .infra-pill");
      expect(pill?.textContent?.toLowerCase()).toBe("ready");
    });
    expect(container.querySelector(".viewer-title .infra-pill")?.className).not.toMatch(/busy/);
  });

  it("still says 'starting' when the default branch is not ready", async () => {
    // The other half: a derived word must not become a cheerful lie.
    mockFetch({ "/tables": { schema: "public", tables: [], truncated: false },
      "/api/lakebase/projects/": page({
        branches: [{ ref: "projects/pg_tickets/branches/production", name: "production",
          isDefault: true, state: "starting" }] }) });
    const { container } = render(<LakebasePage doc={project} workspace={null} />);
    await waitFor(() => {
      expect(container.querySelector(".viewer-title .infra-pill")?.textContent?.toLowerCase())
        .toBe("starting");
    });
  });

  it("keeps three blocks when the branches call is denied", async () => {
    // [E-11] a partial failure is visible, not a blank page
    mockFetch({ "/tables": { schema: "public", tables: [], truncated: false },
      "/api/lakebase/projects/": page({ branches: { error: "you do not have CAN MANAGE" } }) });
    render(<LakebasePage doc={project} workspace={null} />);
    expect(await screen.findByText(/CAN MANAGE/)).toBeInTheDocument();
    // the project block still rendered
    expect(screen.getByText("17")).toBeInTheDocument();
  });

  it("offers no retry for a refusal that cannot change", async () => {
    // [E-1] a CAN MANAGE grant does not appear between two clicks
    mockFetch({ "/tables": { schema: "public", tables: [], truncated: false },
      "/api/lakebase/projects/": page({ project: { error: "PERMISSION_DENIED: you need CAN MANAGE" } }) });
    render(<LakebasePage doc={project} workspace={null} />);
    expect(await screen.findByText(/PERMISSION_DENIED/)).toBeInTheDocument();
  });
});

describe("AppPage", () => {
  const view = (over: Record<string, unknown> = {}) => ({
    name: "tickets_app", url: "https://t-1.example", state: "running", stateRaw: "RUNNING",
    lakebase: "pg_tickets", creator: "me@example.com", computeSize: "MEDIUM",
    deploymentState: "SUCCEEDED",
    resources: [{ name: "postgres", kind: "postgres", permission: "CAN_CONNECT_AND_CREATE",
      branch: "projects/pg/branches/b" }],
    health: { status: 200, ms: 412, state: "running", checkedAt: "10:42:01" },
    ...over,
  });

  it("answers 'is it working' with a status code", async () => {
    // [UI-4], [AP-4]
    mockFetch({ "/api/apps/": view() });
    render(<AppPage doc={app} workspace={null} />);
    expect(await screen.findByText("Answered 200 in 412 ms")).toBeInTheDocument();
    expect(screen.getByText("200", { selector: ".infra-health-code" })).toBeInTheDocument();
  });

  it("calls a cold start normal, not down", async () => {
    // [E-14]
    mockFetch({ "/api/apps/": view({ health: { status: null, ms: 15_000, state: "starting" } }) });
    render(<AppPage doc={app} workspace={null} />);
    expect(await screen.findByText(/Cold start/)).toBeInTheDocument();
    expect(screen.queryByText(/down/i)).not.toBeInTheDocument();
  });

  it("shows the resources and their permission", async () => {
    mockFetch({ "/api/apps/": view() });
    render(<AppPage doc={app} workspace={null} />);
    expect(await screen.findByText("CAN_CONNECT_AND_CREATE")).toBeInTheDocument();
  });

  it("warns when the postgres resource is missing, which is why an app cannot connect", async () => {
    // [F6] the app exists and has no database resource: this is what the defect looked like
    mockFetch({ "/api/apps/": view({ resources: [] }) });
    render(<AppPage doc={app} workspace={null} />);
    expect(await screen.findByText(/No postgres resource/)).toBeInTheDocument();
  });

  it("offers a fix prompt that carries the status code, when the app is failing", async () => {
    // [E-13]
    const asked: string[] = [];
    mockFetch({ "/api/apps/": view({ state: "failing",
      health: { status: 500, ms: 300, state: "failing" } }) });
    render(<AppPage doc={app} workspace={null} onAsk={(p) => asked.push(p)} />);
    const button = await screen.findByRole("button", { name: /Ask the agent to fix it/ });
    button.click();
    expect(asked[0]).toContain("HTTP 500");
    expect(asked[0]).toContain("/logz");
  });

  it("links the logs at /logz", async () => {
    mockFetch({ "/api/apps/": view() });
    render(<AppPage doc={app} workspace={null} />);
    const link = await screen.findByRole("link", { name: "/logz" });
    expect(link).toHaveAttribute("href", "https://t-1.example/logz");
  });
});
