export const NAVIGATION_HISTORY_STORAGE_KEY = "ai_stp_navigation_history";

const MAX_NAVIGATION_ENTRIES = 64;

export type NavigationEntry = {
  href: string;
  scrollY: number;
};

function validEntry(value: unknown): value is NavigationEntry {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as NavigationEntry).href === "string" &&
    (value as NavigationEntry).href.startsWith("/") &&
    typeof (value as NavigationEntry).scrollY === "number" &&
    Number.isFinite((value as NavigationEntry).scrollY)
  );
}

export function getNavigationStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function currentNavigationHref(location: Location): string {
  return `${location.pathname}${location.search}${location.hash}`;
}

export function readNavigationHistory(storage: Storage | null): NavigationEntry[] {
  if (!storage) return [];
  try {
    const parsed: unknown = JSON.parse(storage.getItem(NAVIGATION_HISTORY_STORAGE_KEY) ?? "null");
    return Array.isArray(parsed) ? parsed.filter(validEntry).slice(-MAX_NAVIGATION_ENTRIES) : [];
  } catch {
    return [];
  }
}

function writeNavigationHistory(storage: Storage | null, entries: NavigationEntry[]): void {
  if (!storage) return;
  try {
    storage.setItem(
      NAVIGATION_HISTORY_STORAGE_KEY,
      JSON.stringify(entries.slice(-MAX_NAVIGATION_ENTRIES)),
    );
  } catch {
    // Navigation still works through the browser history when session storage is unavailable.
  }
}

/**
 * Records a route transition and returns the target scroll position for a popstate restore.
 * ponytail: bounded linear scan; the browser history mirror is capped at 64 entries.
 */
export function recordNavigation(
  storage: Storage | null,
  href: string,
  fromPopState: boolean,
  scrollY: number,
): number | null {
  const history = readNavigationHistory(storage);
  if (!history.length) {
    writeNavigationHistory(storage, [{ href, scrollY }]);
    return null;
  }

  if (fromPopState) {
    const targetIndex = history.findLastIndex((entry) => entry.href === href);
    if (targetIndex >= 0) {
      const target = history[targetIndex];
      if (!target) return null;
      writeNavigationHistory(storage, history.slice(0, targetIndex + 1));
      return target.scrollY;
    }
  }

  if (history.at(-1)?.href !== href) {
    writeNavigationHistory(storage, [...history, { href, scrollY }]);
  }
  return null;
}

export function updateCurrentNavigation(
  storage: Storage | null,
  href: string,
  scrollY?: number,
): void {
  const history = readNavigationHistory(storage);
  if (!history.length) {
    writeNavigationHistory(storage, [{ href, scrollY: scrollY ?? 0 }]);
    return;
  }
  const current = history.at(-1);
  writeNavigationHistory(storage, [
    ...history.slice(0, -1),
    { href, scrollY: scrollY ?? current?.scrollY ?? 0 },
  ]);
}

export function canGoBack(storage: Storage | null, href: string): boolean {
  const history = readNavigationHistory(storage);
  return history.length > 1 && history.at(-1)?.href === href;
}
