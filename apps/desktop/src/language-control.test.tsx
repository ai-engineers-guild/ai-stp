// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import LanguageSelect from "./components/LanguageSelect";
import { changeLocale, i18n, loadCatalog, useLocale } from "./i18n";
import { preparePreferences, usePreferences } from "./preferences";
import * as transport from "./transport";

const invoke = vi.hoisted(() => {
  vi.resetModules();
  return vi.fn();
});
vi.mock("@tauri-apps/api/core", () => ({ invoke, isTauri: () => true }));
const reply = () => ({
  ok: true,
  data: { preferences: null },
  warnings: [],
  continuations: [],
  error: null,
  error_code: null,
});
let acknowledgements: (() => void)[] = [];

beforeEach(async () => {
  localStorage.clear();
  acknowledgements = [];
  invoke.mockReset();
  invoke.mockImplementation((command: string) =>
    command === "ui_preferences_read"
      ? Promise.resolve(reply())
      : new Promise((resolve) => {
          acknowledgements.push(() => resolve(reply()));
        }),
  );
  await loadCatalog("en");
  await preparePreferences(transport);
  await changeLocale("en", false);
});

afterEach(async () => {
  await act(async () => {
    await vi.waitFor(() => {
      for (const acknowledge of acknowledgements.splice(0)) acknowledge();
      expect(usePreferences.getState().pending).toBe(false);
    });
  });
  cleanup();
  await changeLocale("en", false);
});

it("keeps the language control focusable while native saving is pending", async () => {
  render(<LanguageSelect />);
  const selector = screen.getByRole("combobox");
  selector.focus();
  await act(async () => {
    fireEvent.change(selector, { target: { value: "ar" } });
    await vi.waitFor(() => expect(acknowledgements).toHaveLength(1));
  });
  expect(i18n.resolvedLanguage).toBe("ar");
  expect(selector).toHaveProperty("disabled", false);
  expect(selector.getAttribute("aria-busy")).toBe("true");
  expect(document.activeElement).toBe(selector);
  await act(async () => {
    acknowledgements.shift()?.();
    await vi.waitFor(() => expect(useLocale.getState().pending).toBe(false));
  });
  expect(selector.getAttribute("aria-busy")).toBe("false");
});

it("does not clear the latest language request when an earlier native save finishes", async () => {
  const first = changeLocale("ar");
  await vi.waitFor(() => expect(acknowledgements).toHaveLength(1));
  const latest = changeLocale("en");
  await vi.waitFor(() => expect(i18n.resolvedLanguage).toBe("en"));
  acknowledgements.shift()?.();
  await first;
  await vi.waitFor(() => expect(acknowledgements).toHaveLength(1));
  expect(useLocale.getState().pending).toBe(true);
  acknowledgements.shift()?.();
  expect(await latest).toBe(true);
  expect(invoke).toHaveBeenLastCalledWith("ui_preferences_write", {
    preferences: { locale: "en", theme: null },
  });
  expect(useLocale.getState().pending).toBe(false);
});
