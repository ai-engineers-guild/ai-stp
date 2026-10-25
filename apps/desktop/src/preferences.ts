// Optional UI preferences cannot prevent startup or an in-memory toggle.
export function readPreference(key: string): string | null {
  try {
    const value = globalThis.localStorage?.getItem?.(key);
    return typeof value === "string" ? value : null;
  } catch {
    return null;
  }
}

export function writePreference(key: string, value: string): void {
  try {
    globalThis.localStorage?.setItem?.(key, value);
  } catch {
    // Keep the current choice for this window even when persistence is denied.
  }
}
