// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from "vitest";

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke, isTauri: () => true }));
const reply = (preferences: unknown = null) => ({
  ok: true,
  data: { preferences },
  warnings: [],
  continuations: [],
  error: null,
  error_code: null,
});

beforeEach(() => {
  vi.resetModules();
  invoke.mockReset();
  localStorage.clear();
});

it("restores acknowledged native choices before legacy browser preferences", async () => {
  localStorage.setItem("ai-stp.locale", "ru");
  invoke.mockResolvedValue(reply({ locale: "ar", theme: "dark" }));
  const { preparePreferences, readPreference } = await import("./preferences");
  await preparePreferences(await import("./transport"));
  expect(readPreference("ai-stp.locale")).toBe("ar");
  expect(readPreference("ai-stp.theme")).toBe("dark");
});

it("waits for native acknowledgement and keeps the latest language with its theme", async () => {
  let acknowledge!: (value: unknown) => void;
  invoke
    .mockResolvedValueOnce(reply())
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          acknowledge = resolve;
        }),
    )
    .mockResolvedValue(reply());
  const {
    preparePreferences,
    readPreference,
    usePreferences,
    writePreference,
  } = await import("./preferences");
  await preparePreferences(await import("./transport"));
  const first = writePreference("ai-stp.theme", "dark");
  const last = writePreference("ai-stp.locale", "ar");
  await vi.waitFor(() => expect(invoke).toHaveBeenCalledTimes(2));
  expect(usePreferences.getState().pending).toBe(true);
  acknowledge(reply());
  expect(await Promise.all([first, last])).toEqual([true, true]);
  expect(invoke).toHaveBeenLastCalledWith("ui_preferences_write", {
    preferences: { locale: "ar", theme: "dark" },
  });
  expect(readPreference("ai-stp.locale")).toBe("ar");
  expect(usePreferences.getState()).toEqual({ pending: false, failed: false });
});

it("keeps the current choice and a recoverable failure when native saving refuses", async () => {
  invoke
    .mockResolvedValueOnce(reply())
    .mockRejectedValueOnce(new Error("Disk unavailable"));
  const {
    preparePreferences,
    readPreference,
    usePreferences,
    writePreference,
  } = await import("./preferences");
  await preparePreferences(await import("./transport"));
  expect(await writePreference("ai-stp.locale", "kk")).toBe(false);
  expect(readPreference("ai-stp.locale")).toBe("kk");
  expect(usePreferences.getState()).toEqual({ pending: false, failed: true });
  invoke.mockResolvedValue(reply());
  expect(await writePreference("ai-stp.locale", "kk")).toBe(true);
  expect(usePreferences.getState().failed).toBe(false);
});
