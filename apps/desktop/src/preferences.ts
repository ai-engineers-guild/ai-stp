import { isTauri } from "@tauri-apps/api/core";
import { create } from "zustand";
import configuration from "./localization.json";
import type { UiPreferences } from "./generated/native";

export const usePreferences = create(() => ({ pending: false, failed: false }));
let native: UiPreferences | null = null;
let saving = Promise.resolve();
let pendingWrites = 0;
type PreferenceIo = Pick<
  typeof import("./transport"),
  "cmdPreferencesRead" | "cmdPreferencesWrite"
>;
let backend: PreferenceIo | undefined;

function browserPreference(key: string): string | null {
  try {
    const value = globalThis.localStorage?.getItem?.(key);
    return typeof value === "string" ? value : null;
  } catch {
    return null;
  }
}

/** Native acknowledged storage wins; existing browser choices migrate on the next save. */
export async function preparePreferences(io: PreferenceIo): Promise<void> {
  if (!isTauri()) return;
  backend = io;
  const reply = await io.cmdPreferencesRead();
  const preferences = reply.data?.preferences as
    | UiPreferences
    | null
    | undefined;
  const locale = browserPreference("ai-stp.locale");
  const theme = browserPreference("ai-stp.theme");
  native = preferences ?? {
    locale:
      locale && Object.hasOwn(configuration.languages, locale) ? locale : null,
    theme: theme === "dark" || theme === "light" ? theme : null,
  };
  usePreferences.setState({ failed: !reply.ok });
}

export function readPreference(key: string): string | null {
  if (native) {
    if (key === "ai-stp.locale") return native.locale;
    if (key === "ai-stp.theme") return native.theme;
  }
  return browserPreference(key);
}

/** Apply in memory immediately; serialize native saves so the latest full snapshot wins. */
export async function writePreference(
  key: string,
  value: string,
): Promise<boolean> {
  try {
    globalThis.localStorage?.setItem?.(key, value);
  } catch {
    // Browser previews keep their choice in memory even when storage is denied.
  }
  if (!isTauri() || (key !== "ai-stp.locale" && key !== "ai-stp.theme"))
    return true;
  const field = key === "ai-stp.locale" ? "locale" : "theme";
  native = { ...(native ?? { locale: null, theme: null }), [field]: value };
  const snapshot = { ...native };
  pendingWrites += 1;
  usePreferences.setState({ pending: true });
  let saved = false;
  const request = saving.then(async () => {
    saved = backend ? (await backend.cmdPreferencesWrite(snapshot)).ok : false;
    usePreferences.setState({ failed: !saved });
  });
  saving = request.catch(() => {
    usePreferences.setState({ failed: true });
  });
  await saving;
  pendingWrites -= 1;
  usePreferences.setState({ pending: pendingWrites !== 0 });
  return saved;
}
