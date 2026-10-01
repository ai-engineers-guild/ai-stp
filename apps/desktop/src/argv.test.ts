import { describe, expect, it } from "vitest";
import { argvToCall } from "./argv";

const APPLY = ["install", "apply"];

describe("argvToCall", () => {
  it("parses a flag-valued continuation", () => {
    expect(
      argvToCall(APPLY, ["install", "apply", "--operation", "op_123", "--json"]),
    ).toEqual({ path: "install apply", values: { operation: "op_123" }, flags: [] });
  });

  it("parses boolean flags and mixed values", () => {
    expect(
      argvToCall(["task", "answer"], ["task", "answer", "--task", "t1", "--revision", "3", "--force"]),
    ).toEqual({
      path: "task answer",
      values: { task: "t1", revision: "3" },
      flags: ["force"],
    });
  });

  it("uses the declared path, not argv words", () => {
    const r = argvToCall(["a", "b"], ["a", "b", "--x", "1"]);
    expect(r?.path).toBe("a b");
  });

  it("refuses positionals after the declared path", () => {
    expect(argvToCall(APPLY, ["install", "apply", "stray", "--operation", "x"])).toBeNull();
  });

  it("refuses when the declared path is missing from argv", () => {
    // declared 3 words but argv only carries 2 — slice leaves "apply" as a
    // positional → refuse rather than misalign flags
    expect(argvToCall(["a", "b", "c"], ["a", "b", "--x"])).toBeNull();
  });

  it("refuses an empty path", () => {
    expect(argvToCall([], ["--json"])).toBeNull();
  });

  it("refuses an empty argv", () => {
    expect(argvToCall(APPLY, [])).toBeNull();
  });

  it("keeps values that look like paths or ids", () => {
    const r = argvToCall(
      ["task", "answer"],
      ["task", "answer", "--task", "task_01X", "--question-id", "project-root", "--value", "/home/u/proj"],
    );
    expect(r?.values["value"]).toBe("/home/u/proj");
  });

  it("treats a value that starts with -- as a flag, not a value", () => {
    const r = argvToCall(["x", "y"], ["x", "y", "--a", "--b", "v"]);
    expect(r).toEqual({ path: "x y", values: { b: "v" }, flags: ["a"] });
  });
});
