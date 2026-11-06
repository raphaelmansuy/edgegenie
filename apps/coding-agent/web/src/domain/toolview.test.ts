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
});
