import { describe, expect, it } from "vitest";
import { errorText } from "./apierror";

describe("errorText", () => {
  it("passes a plain refusal through", () => {
    expect(errorText({ detail: "Google Vertex AI needs a key" }, "x")).toBe("Google Vertex AI needs a key");
  });
  it("reads a credential form's nested detail", () => {
    expect(errorText({ detail: { detail: "not a valid key", field: "secret" } }, "x")).toBe("not a valid key");
  });
  it("turns FastAPI's validation list into field: message", () => {
    const body = { detail: [{ loc: ["body", "folder"], msg: "String should have at least 1 character" }] };
    expect(errorText(body, "x")).toBe("folder: String should have at least 1 character");
  });
  it("falls back to the status text, never to raw JSON", () => {
    expect(errorText({}, "Bad Gateway")).toBe("Bad Gateway");
    expect(errorText(null, "Bad Gateway")).toBe("Bad Gateway");
  });
});
