/** The blob rules, tested against the same expectations as the server's.
 *
 * The most important test here is the last one: the two copy registers must have the same keys. That is
 * the only mechanism that keeps a client-side refusal and a server-side refusal saying the same thing.
 */
import { describe, expect, it } from "vitest";
import {
  ACCEPT, MAX_ATTACHMENTS, MAX_BYTES, REFUSALS, familyOf, humanSize, pastedName, refuse, sanitiseName, say,
} from "./blob";

const file = (name: string, size: number, type = "") =>
  new File([new Uint8Array(Math.min(size, 16))], name, { type });

/** A File whose reported size we control, without allocating it. */
const sized = (name: string, size: number, type = "") => {
  const f = new File([new Uint8Array(0)], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
};

const opts = { count: 0, modelSeesImages: true, model: "llama-4-maverick" };

describe("humanSize", () => {
  it("uses the unit a person would", () => {
    expect(humanSize(900)).toBe("900 bytes");
    expect(humanSize(2048)).toBe("2 KB");
    expect(humanSize(12_400_000)).toBe("11.8 MB");
  });
});

describe("sanitiseName", () => {
  it("keeps a basename and drops the path", () => {
    expect(sanitiseName("/a/b/report.png")).toBe("report.png");
    expect(sanitiseName("..\\..\\x.png")).toBe("x.png");
  });
  it("collapses runs of punctuation rather than doubling them", () => {
    expect(sanitiseName("weird<>.txt")).toBe("weird_.txt");
  });
  it("refuses a name that is only dots", () => {
    expect(sanitiseName("..")).toBe("");
  });
  it("truncates but keeps the extension", () => {
    const out = sanitiseName(`${"x".repeat(400)}.png`);
    expect(out.length).toBeLessThanOrEqual(120);
    expect(out.endsWith(".png")).toBe(true);
  });
});

describe("familyOf", () => {
  it("knows an image from its type", () => {
    expect(familyOf(file("a.png", 10, "image/png"))).toBe("image");
  });
  it("treats a text extension as text", () => {
    expect(familyOf(file("a.csv", 10, "text/csv"))).toBe("text");
  });
  it("recognises a notebook", () => {
    expect(familyOf(file("a.ipynb", 10))).toBe("notebook");
  });
  it("treats an unknown binary type as other", () => {
    expect(familyOf(file("a.exe", 10, "application/x-msdownload"))).toBe("other");
  });
});

describe("pastedName", () => {
  it("names a pasted image and a pasted file differently", () => {
    const at = new Date(2026, 10, 9, 7, 6, 5);
    expect(pastedName("image/png", at)).toBe("pasted-20261109-070605.png");
    expect(pastedName("text/csv", at)).toBe("pasted-20261109-070605");
  });
});

describe("refuse", () => {
  it("accepts a reasonable image", () => {
    expect(refuse(sized("shot.png", 400_000, "image/png"), opts)).toBeNull();
  });

  it("refuses one byte over the limit, naming both values", () => {
    const r = refuse(sized("big.png", MAX_BYTES + 1, "image/png"), opts);
    expect(r?.code).toBe("too_big");
    expect(r?.message).toContain("8.0 MB");
    expect(r?.message).toContain("big.png");
  });

  it("accepts exactly at the limit", () => {
    expect(refuse(sized("big.png", MAX_BYTES, "image/png"), opts)).toBeNull();
  });

  it("refuses an empty file", () => {
    expect(refuse(sized("e.txt", 0, "text/plain"), opts)?.code).toBe("empty");
  });

  it("refuses more than the limit, naming the limit", () => {
    const r = refuse(sized("a.png", 10, "image/png"), { ...opts, count: MAX_ATTACHMENTS });
    expect(r?.code).toBe("too_many");
    expect(r?.message).toContain(String(MAX_ATTACHMENTS));
  });

  it("ACCEPTS an image when the model cannot see, rather than leaving the user no way to attach it", () => {
    // [P4]: the unacceptable case is an attachment the model silently cannot see. The chip says so, and the
    // manifest says so — but the bytes are the user's evidence and are not refused on the model's behalf.
    expect(refuse(sized("shot.png", 100, "image/png"), { ...opts, modelSeesImages: false })).toBeNull();
  });

  it("never refuses text for want of vision", () => {
    expect(refuse(sized("a.csv", 100, "text/csv"), { ...opts, modelSeesImages: false })).toBeNull();
  });
});

describe("the copy register", () => {
  it("every sentence ends with a full stop and exhales nothing", () => {
    for (const [code, sentence] of Object.entries(REFUSALS)) {
      expect(sentence.endsWith("."), code).toBe(true);
      expect(sentence.includes("!"), code).toBe(false);
    }
  });

  it("fills placeholders", () => {
    expect(say("too_big", { name: "a.png", size: "9.0 MB", limit: "8.0 MB" }))
      .toBe("a.png is 9.0 MB; the limit is 8.0 MB.");
  });

  it("names both numbers in a size refusal", () => {
    expect(REFUSALS.too_big).toContain("{size}");
    expect(REFUSALS.too_big).toContain("{limit}");
  });
});

describe("ACCEPT", () => {
  it("lists the image types the server verifies", () => {
    for (const t of ["image/png", "image/jpeg", "image/webp", "image/gif"]) {
      expect(ACCEPT).toContain(t);
    }
  });
});
