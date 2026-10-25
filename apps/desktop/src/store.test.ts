import { afterEach, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

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
