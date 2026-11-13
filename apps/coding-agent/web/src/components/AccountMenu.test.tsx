import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AccountMenu } from "./AccountMenu";
import { COMPILED, DOCS_URL, RELEASES_URL, SOURCE_URL, versionLabel, versionTitle, withServer } from "../domain/version";

afterEach(cleanup);

const open = () => fireEvent.click(screen.getByRole("button", { name: /^Account:/ }));

describe("the account menu states which build this is", () => {
  it("shows the version, linked to the release history", () => {
    render(<AccountMenu user="ada@example.com" host="https://dbc-x.cloud.databricks.com" folder="/Users/ada"
      demo={false} build={{ version: "1.0.0", commit: "abc1234", built: COMPILED.built }}
      onProviders={() => {}} onKeys={() => {}} />);
    open();
    const facts = screen.getByText("Version").closest("dl")!;
    const link = facts.querySelector("a.version-link") as HTMLAnchorElement;
    // The version number is an answer, so the row is a link to what a version number asks for next.
    expect(link.textContent).toBe("v1.0.0 · abc1234");
    expect(link.getAttribute("href")).toBe(RELEASES_URL);
    expect(link.getAttribute("title")).toContain("OpenGenie v1.0.0");
  });

  it("says when a deployment reports no commit, instead of showing a blank", () => {
    render(<AccountMenu user="ada@example.com" host={null} folder="" demo={false}
      build={{ version: "1.0.0", commit: "", built: COMPILED.built }} onProviders={() => {}} onKeys={() => {}} />);
    open();
    // A Workspace-folder deployment has no `.git`; an empty string here would read as a rendering bug.
    expect(screen.getByText(/no commit reported/)).toBeInTheDocument();
  });

  it("offers Documentation and Source as menu items, not only through the version", () => {
    render(<AccountMenu user="ada@example.com" host={null} folder="" demo={false} build={COMPILED}
      onProviders={() => {}} onKeys={() => {}} />);
    open();
    const docs = screen.getByRole("menuitem", { name: /Documentation/ });
    const source = screen.getByRole("menuitem", { name: /Source code/ });
    expect(docs.getAttribute("href")).toBe(DOCS_URL);
    expect(source.getAttribute("href")).toBe(SOURCE_URL);
    // New tab, no opener: the page is being read, not replaced.
    for (const el of [docs, source]) {
      expect(el.getAttribute("target")).toBe("_blank");
      expect(el.getAttribute("rel")).toContain("noopener");
    }
  });

  it("still works with no build facts at all, so an old caller cannot crash the bar", () => {
    render(<AccountMenu user="ada@example.com" host={null} folder="" demo={false}
      onProviders={() => {}} onKeys={() => {}} />);
    open();
    expect(screen.queryByText("Version")).toBeNull();
    expect(screen.getByText("ada@example.com")).toBeInTheDocument();
  });
});

describe("version facts", () => {
  it("labels a version with and without a commit", () => {
    expect(versionLabel({ version: "1.0.0", commit: "", built: "" })).toBe("v1.0.0");
    expect(versionLabel({ version: "1.0.0", commit: "abc1234", built: "" })).toBe("v1.0.0 · abc1234");
  });

  it("explains an absent commit in the tooltip rather than leaving it unexplained", () => {
    expect(versionTitle({ version: "1.0.0", commit: "", built: "" })).toContain("no commit reported");
    expect(versionTitle({ version: "1.0.0", commit: "abc1234", built: "" })).toContain("resolved");
  });

  it("lets the server's answer win over the compiled one, without erasing what only the bundle knows", () => {
    const compiled = { version: "0.0.0", commit: "", built: "2026-11-11T00:00:00.000Z" };
    const merged = withServer(compiled, { version: "1.0.0", commit: "d5efcfd1" });
    expect(merged.version).toBe("1.0.0");
    expect(merged.commit).toBe("d5efcfd1");
    expect(merged.built).toBe(compiled.built);
    // An empty server commit must not blank the compiled one either.
    expect(withServer({ ...compiled, commit: "abc" }, { version: "1.0.0", commit: "" }).commit).toBe("abc");
    // And no answer at all is a no-op.
    expect(withServer(compiled, null)).toEqual(compiled);
  });

  it("keeps the compiled facts from the build, never an empty version", () => {
    // `vite.config.ts` and the test setup both assign these; an unassigned global would be `unknown`.
    expect(COMPILED.version).toMatch(/^\d+\.\d+\.\d+/);
    expect(COMPILED.commit).not.toBe("");
  });
});
