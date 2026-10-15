import { afterEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { cliApplyConfirmed, cmdTaskStart, cmdVersion } from "./transport";
import { useDebug } from "./store";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
afterEach(() => {
  vi.resetAllMocks();
  useDebug.setState({ debugMode: false, log: [] });
});
it("returns a structured failure when IPC throws synchronously", async () => {
  vi.mocked(invoke).mockImplementation(() => {
    throw new Error("No native bridge");
  });
  expect(await cmdVersion()).toMatchObject({
    ok: false,
    error_code: "IPC_THROW",
  });
});
it("does not retain form content or generic task answers in a diagnostic trace", async () => {
  useDebug.setState({ debugMode: true });
  vi.mocked(invoke).mockResolvedValue({
    ok: true,
    data: {},
    error: null,
    error_code: null,
    warnings: [],
    continuations: [],
  });
  await cmdTaskStart("author", "desktop-test-key-01", undefined, {
    name: "private user input",
  });
  await cliApplyConfirmed(
    "task answer",
    { value: "another private answer" },
    [],
    true,
  );
  const log = JSON.stringify(useDebug.getState().log);
  expect(log).not.toContain("private user input");
  expect(log).not.toContain("another private answer");
  expect(log).toContain("[task input]");
  expect(log).toContain("[user answer]");
});
