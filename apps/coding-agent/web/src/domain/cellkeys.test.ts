import { describe, expect, it } from "vitest";
import { commandKey, runChord, type KeyLike } from "./cellkeys";

const key = (k: string, o: Partial<KeyLike> = {}): KeyLike => ({ key: k, shiftKey: false, metaKey: false, ctrlKey: false, altKey: false, ...o });

describe("run chords (both modes)", () => {
  it("maps Shift+Enter, ⌘/Ctrl+Enter and Alt+Enter", () => {
    expect(runChord(key("Enter", { shiftKey: true }))).toEqual({ type: "run", advance: "next" });
    expect(runChord(key("Enter", { metaKey: true }))).toEqual({ type: "run", advance: "stay" });
    expect(runChord(key("Enter", { ctrlKey: true }))).toEqual({ type: "run", advance: "stay" });
    expect(runChord(key("Enter", { altKey: true }))).toEqual({ type: "run", advance: "insert" });
  });
  it("leaves a plain Enter and other chords alone", () => {
    expect(runChord(key("Enter"))).toBeNull();
    expect(runChord(key("Enter", { shiftKey: true, metaKey: true }))).toBeNull();
    expect(runChord(key("a", { shiftKey: true }))).toBeNull();
  });
});

describe("command mode", () => {
  it("navigates with arrows, j/k and p/n", () => {
    expect(commandKey(key("ArrowDown"), "").command).toEqual({ type: "select", to: "next" });
    expect(commandKey(key("k"), "").command).toEqual({ type: "select", to: "prev" });
    expect(commandKey(key("p"), "").command).toEqual({ type: "select", to: "prev" });
    expect(commandKey(key("End"), "").command).toEqual({ type: "select", to: "last" });
  });
  it("Enter edits; Shift+Enter runs and moves on", () => {
    expect(commandKey(key("Enter"), "").command).toEqual({ type: "edit" });
    expect(commandKey(key("Enter", { shiftKey: true }), "").command).toEqual({ type: "run", advance: "next" });
  });
  it("inserts, converts and moves", () => {
    expect(commandKey(key("a"), "").command).toEqual({ type: "insert", where: "above" });
    expect(commandKey(key("b"), "").command).toEqual({ type: "insert", where: "below" });
    expect(commandKey(key("m"), "").command).toEqual({ type: "convert", kind: "markdown" });
    expect(commandKey(key("y"), "").command).toEqual({ type: "convert", kind: "code" });
    expect(commandKey(key("ArrowUp", { altKey: true }), "").command).toEqual({ type: "move", by: -1 });
  });
  it("deletes only on a second D, and any other key disarms", () => {
    const first = commandKey(key("d"), "");
    expect(first).toEqual({ command: null, armed: "d" });
    expect(commandKey(key("d"), first.armed)).toEqual({ command: { type: "delete" }, armed: "" });
    expect(commandKey(key("j"), "d").armed).toBe("");
    expect(commandKey(key("x"), "d")).toEqual({ command: null, armed: "" });
  });
  it("GG goes to the first cell and Shift+G to the last", () => {
    const first = commandKey(key("g"), "");
    expect(first.armed).toBe("g");
    expect(commandKey(key("g"), "g").command).toEqual({ type: "select", to: "first" });
    expect(commandKey(key("G", { shiftKey: true }), "").command).toEqual({ type: "select", to: "last" });
  });
  it("II stops, 00 clears, O folds, Shift+M merges", () => {
    expect(commandKey(key("i"), "i").command).toEqual({ type: "stop" });
    expect(commandKey(key("0"), "0").command).toEqual({ type: "clearOutputs" });
    expect(commandKey(key("o"), "").command).toEqual({ type: "output" });
    expect(commandKey(key("M", { shiftKey: true }), "").command).toEqual({ type: "merge" });
  });
  it("extends the selection and copies cells", () => {
    expect(commandKey(key("ArrowDown", { shiftKey: true }), "").command).toEqual({ type: "select", to: "next", extend: true });
    expect(commandKey(key("a", { metaKey: true }), "").command).toEqual({ type: "selectAll" });
    expect(commandKey(key("c", { metaKey: true }), "").command).toEqual({ type: "clipboard", op: "copy" });
  });
  it("runs a range with Alt+Shift", () => {
    expect(commandKey(key("Enter", { altKey: true, shiftKey: true }), "").command).toEqual({ type: "runSpan", span: "all" });
    expect(commandKey(key("ArrowUp", { altKey: true, shiftKey: true }), "").command).toEqual({ type: "runSpan", span: "above" });
    expect(commandKey(key("ArrowDown", { altKey: true, shiftKey: true }), "").command).toEqual({ type: "runSpan", span: "below" });
  });
  it("undoes with z and ⌘Z", () => {
    expect(commandKey(key("z"), "").command).toEqual({ type: "undo" });
    expect(commandKey(key("z", { metaKey: true }), "").command).toEqual({ type: "undo" });
  });
  it("does not swallow browser chords", () => {
    expect(commandKey(key("r", { metaKey: true }), "").command).toBeNull();
    expect(commandKey(key("b", { shiftKey: true }), "").command).toBeNull();
  });
});
