import { afterEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import {
  cliApplyConfirmed,
  cliPlan,
  cmdProfileApply,
  cmdRunRead,
  cmdTaskStart,
  cmdVersion,
} from "./transport";
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

it("keeps company content out of the shared trace while returning the full reply to its caller", async () => {
  useDebug.setState({ debugMode: true });
  const reply = {
    ok: true,
    data: {
      name: "canary-company-directory",
      root: "/canary/private/repository",
    },
    error: null,
    error_code: null,
    warnings: ["canary-company-warning"],
    continuations: [],
  };
  vi.mocked(invoke).mockResolvedValue(reply);
  expect(
    await cmdRunRead("corporate catalog search", {
      context: "context_fixture",
      query: "canary-company-query",
    }),
  ).toBe(reply);
  await cliPlan("corporate assignments preview", {
    context: "context_fixture",
    project: "canary-company-project",
  });
  await cmdRunRead("context list");
  await cmdProfileApply(
    "context apply",
    { label: "canary-company-label" },
    "sha256:fixture",
    true,
  );
  vi.mocked(invoke).mockResolvedValue({
    ...reply,
    ok: false,
    error: "canary-company-error",
    error_code: "FORBIDDEN",
  });
  expect((await cmdRunRead("corporate teams")).error).toBe(
    "canary-company-error",
  );
  vi.mocked(invoke).mockRejectedValue(new Error("canary-company-transport"));
  expect((await cmdRunRead("corporate projects")).error_code).toBe("IPC_THROW");
  const entries = useDebug.getState().log;
  expect(entries).toHaveLength(6);
  expect(JSON.stringify(entries)).not.toContain("canary");
  expect(entries.every((entry) => entry.result === undefined)).toBe(true);
  expect(entries.some((entry) => entry.error_code === "FORBIDDEN")).toBe(true);
  expect(entries[0].error_code).toBe("IPC_THROW");
});
