import { afterEach, expect, it, vi } from "vitest";
import type { CmdResult } from "./transport";

vi.mock("./transport", () => ({
  cmdAuthStatus: vi.fn(),
  cmdCapabilities: vi.fn(),
  cmdDoctor: vi.fn(),
  cmdRunRead: vi.fn(),
  cmdVersion: vi.fn(),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
  vi.resetAllMocks();
});

it.each([true, false])(
  "does not replace a newer account observation with an old successful reply: %s",
  async (success) => {
    const { useApp } = await import("./store");
    const { cmdAuthStatus } = await import("./transport");
    let finish!: (value: CmdResult) => void;
    const latest: CmdResult = {
      ok: success,
      data: success ? { session: { state: "absent" } } : null,
      error: success ? null : "Session unavailable",
      error_code: success ? null : "SESSION_REVOKED",
      warnings: [],
      continuations: [],
    };
    vi.mocked(cmdAuthStatus)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValueOnce(latest);
    const previous = useApp.getState().refreshAuth();
    await useApp.getState().refreshAuth();
    finish({
      ...latest,
      ok: true,
      error: null,
      error_code: null,
      data: {
        session: { state: "authorized", account_id: "previous-account" },
      },
    });
    await previous;
    expect(useApp.getState().authResult).toBe(latest);
    expect(useApp.getState().auth).toBe(latest.data);
  },
);

it.each([
  undefined,
  {},
  {
    getItem: () => {
      throw new Error("Storage denied");
    },
    setItem: () => {
      throw new Error("Storage denied");
    },
  },
])(
  "starts and toggles diagnostics when preference storage is unavailable: %j",
  async (storage) => {
    vi.stubGlobal("localStorage", storage);
    const { useDebug } = await import("./store");
    expect(useDebug.getState().debugMode).toBe(false);
    useDebug.getState().setDebugMode(true);
    expect(useDebug.getState().debugMode).toBe(true);
    useDebug.getState().setDebugMode(false);
    expect(useDebug.getState().debugMode).toBe(false);
  },
);

it("reads and retains an explicit diagnostic preference when storage works", async () => {
  const storage = { getItem: vi.fn(() => "1"), setItem: vi.fn() };
  vi.stubGlobal("localStorage", storage);
  const { useDebug } = await import("./store");
  expect(useDebug.getState().debugMode).toBe(true);
  useDebug.getState().setDebugMode(false);
  expect(storage.setItem).toHaveBeenCalledWith("ai-stp.debug", "0");
});
