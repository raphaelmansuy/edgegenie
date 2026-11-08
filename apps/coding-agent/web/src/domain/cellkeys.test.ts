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
  it("navigates with arrows and j/k", () => {
    expect(commandKey(key("ArrowDown"), false).command).toEqual({ type: "select", to: "next" });
    expect(commandKey(key("k"), false).command).toEqual({ type: "select", to: "prev" });
    expect(commandKey(key("End"), false).command).toEqual({ type: "select", to: "last" });
  });
  it("Enter edits; Shift+Enter runs and moves on", () => {
    expect(commandKey(key("Enter"), false).command).toEqual({ type: "edit" });
    expect(commandKey(key("Enter", { shiftKey: true }), false).command).toEqual({ type: "run", advance: "next" });
  });
  it("inserts, converts and moves", () => {
    expect(commandKey(key("a"), false).command).toEqual({ type: "insert", where: "above" });
    expect(commandKey(key("b"), false).command).toEqual({ type: "insert", where: "below" });
    expect(commandKey(key("m"), false).command).toEqual({ type: "convert", kind: "markdown" });
    expect(commandKey(key("y"), false).command).toEqual({ type: "convert", kind: "code" });
    expect(commandKey(key("ArrowUp", { altKey: true }), false).command).toEqual({ type: "move", by: -1 });
  });
  it("deletes only on a second D, and any other key disarms", () => {
    const first = commandKey(key("d"), false);
    expect(first).toEqual({ command: null, armed: true });
    expect(commandKey(key("d"), first.armed)).toEqual({ command: { type: "delete" }, armed: false });
    expect(commandKey(key("j"), true).armed).toBe(false);
    expect(commandKey(key("x"), true)).toEqual({ command: null, armed: false });
  });
  it("undoes with z and ⌘Z", () => {
    expect(commandKey(key("z"), false).command).toEqual({ type: "undo" });
    expect(commandKey(key("z", { metaKey: true }), false).command).toEqual({ type: "undo" });
  });
  it("does not swallow browser chords", () => {
    expect(commandKey(key("r", { metaKey: true }), false).command).toBeNull();
    expect(commandKey(key("a", { metaKey: true }), false).command).toBeNull();
    expect(commandKey(key("b", { shiftKey: true }), false).command).toBeNull();
  });
});
