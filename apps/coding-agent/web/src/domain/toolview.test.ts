import { describe, expect, it } from "vitest";
import { stripEvidence, subject } from "./toolview";

describe("tool subject", () => {
  it("picks the one thing the call is about", () => {
    expect(subject('{"full_name": "samples.nyctaxi.trips", "limit": 10}')).toBe("samples.nyctaxi.trips");
    expect(subject('{"path": "/Users/a/agent_scratch/hello"}')).toBe("/Users/a/agent_scratch/hello");
    expect(subject('{"sql": "select 1\\nfrom t"}')).toBe("select 1 from t");
    expect(subject('{"todos": [{"content": "a"}, {"content": "b"}]}')).toBe("2 items");
  });
  it("never shows {} or an empty string, and truncates long text", () => {
    expect(subject("{}")).toBe("");
    expect(subject("")).toBe("");
    expect(subject('{"full_name": ""}')).toBe("");
    expect(subject(`{"path": "/${"x".repeat(200)}"}`).length).toBeLessThanOrEqual(90);
  });
  it("falls back to readable text for arguments that are not JSON", () => {
    expect(subject("samples.nyctaxi.trips")).toBe("samples.nyctaxi.trips");
    expect(subject('[{"type":"text","text":"hi"}]')).toContain("type");
  });
});

describe("stripEvidence", () => {
  it("removes the trailing EVIDENCE table, which the panel already shows", () => {
    const a = "Done.\n\nEVIDENCE\n\n| requirement | tool | summary |\n|---|---|---|\n| x | y | z |";
    expect(stripEvidence(a)).toBe("Done.");
    expect(stripEvidence("**Evidence**\n| a | b |\n|---|---|")).toBe("");
  });
  it("leaves an answer with no evidence section alone", () => {
    expect(stripEvidence("Done. No table here.")).toBe("Done. No table here.");
    expect(stripEvidence("")).toBe("");
  });
  it.each([
    ["## Evidence", true], ["### **EVIDENCE**", true], ["  evidence  ", true], ["**Evidence:**", false],
    ["Evidence of rain", false], ["##### Evidence", false], ["the evidence", false], ["", false],
  ])("heading %j -> %s", (line, yes) => {
    expect(stripEvidence(`Answer.\n${line}\n| a |`)).toBe(yes ? "Answer." : `Answer.\n${line}\n| a |`);
  });

  // Regression: `^\s*#{0,4}\s*\**\s*EVIDENCE\s*\**\s*$` backtracked cubically. 500 blank lines took
  // 65 s and froze the tab ("Page Unresponsive") while a model padded its answer. Linear now.
  it.each([
    ["blank lines", "\n"], ["spaces", " "], ["asterisks", "*"], ["blank lines with spaces", " \n"],
  ])("stays fast on a very long run of %s", (_n, unit) => {
    const text = `Answer.\n${unit.repeat(200_000)}tail`;
    const t0 = performance.now();
    expect(stripEvidence(text)).toBe(text);
    expect(stripEvidence(`${text}\nEVIDENCE\n| x |`)).toBe(text.trimEnd());
    expect(performance.now() - t0).toBeLessThan(500);
  });
});
