// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from "vitest";
import { useTaskStart } from "./taskStart";
import { cmdTaskStart, type CmdResult } from "./transport";

vi.mock("./transport", () => ({ cmdTaskStart: vi.fn() }));
const unconfirmed: CmdResult = {
  ok: false, data: null, error: "Reply lost", error_code: "AI_STP_TIMEOUT_UNCONFIRMED",
  warnings: [], continuations: [],
};
beforeEach(() => {
  vi.resetAllMocks();
  useTaskStart.getState().reset();
  vi.mocked(cmdTaskStart).mockResolvedValue(unconfirmed);
});

it("does not give another request the running task's promise or result", async () => {
  let complete!: (result: CmdResult) => void;
  vi.mocked(cmdTaskStart).mockReturnValue(new Promise((resolve) => { complete = resolve; }));
  const original = useTaskStart.getState().start({ intent: "author" });
  const same = useTaskStart.getState().start({ intent: "author" });
  const other = useTaskStart.getState().start({ intent: "install" });
  try {
    expect(same).toBe(original);
    expect(other).not.toBe(original);
    expect((await other).error_code).toBe("DESKTOP_TASK_START_CONFLICT");
    expect(useTaskStart.getState().request).toEqual({ intent: "author" });
  } finally {
    complete(unconfirmed);
    await original;
  }
  expect(cmdTaskStart).toHaveBeenCalledTimes(1);
});

it("detaches the admitted request from caller mutation and reuses its semantic retry key", async () => {
  const request = { intent: "install", input: { setup: "original", targets: { project: "/original" } } };
  const first = useTaskStart.getState().start(request);
  request.input.setup = "other";
  request.input.targets.project = "/other";
  await first;
  const key = useTaskStart.getState().key;
  expect(cmdTaskStart).toHaveBeenLastCalledWith("install", key, undefined,
    { setup: "original", targets: { project: "/original" } });
  expect(Object.isFrozen(useTaskStart.getState().request?.input)).toBe(true);
  await useTaskStart.getState().start({ input: { targets: { project: "/original" }, setup: "original" }, intent: "install" });
  expect(cmdTaskStart).toHaveBeenCalledTimes(2);
  expect(useTaskStart.getState().key).toBe(key);
});

it("keeps an uncertain original until a separate request is explicitly chosen", async () => {
  await useTaskStart.getState().start({ intent: "author" });
  const key = useTaskStart.getState().key;
  const conflict = await useTaskStart.getState().start({ intent: "install" });
  expect(conflict.error_code).toBe("DESKTOP_TASK_START_CONFLICT");
  expect(useTaskStart.getState().key).toBe(key);
  expect(useTaskStart.getState().result).toEqual(unconfirmed);
  expect(cmdTaskStart).toHaveBeenCalledTimes(1);
  useTaskStart.getState().reset();
  await useTaskStart.getState().start({ intent: "install" });
  expect(cmdTaskStart).toHaveBeenCalledTimes(2);
  expect(useTaskStart.getState().key).not.toBe(key);
});

it("retains the same request after an unexpected transport rejection", async () => {
  vi.mocked(cmdTaskStart).mockRejectedValueOnce(new Error("private transport canary"));
  const first = await useTaskStart.getState().start({ intent: "author" });
  const key = useTaskStart.getState().key;
  expect(first.error_code).toBe("DESKTOP_TASK_START_UNCONFIRMED");
  expect(JSON.stringify(first)).not.toContain("private transport canary");
  expect(useTaskStart.getState().busy).toBe(false);
  await useTaskStart.getState().start({ intent: "author" });
  expect(useTaskStart.getState().key).toBe(key);
});

it("refuses non-JSON input before allocating or dispatching a task start", async () => {
  const result = await useTaskStart.getState().start({ intent: "author", input: { invalid: 1n } });
  expect(result.ok).toBe(false);
  expect(cmdTaskStart).not.toHaveBeenCalled();
  expect(useTaskStart.getState().key).toBeNull();
});
