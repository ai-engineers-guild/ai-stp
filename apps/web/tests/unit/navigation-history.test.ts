import { afterEach, describe, expect, it, vi } from "vitest";

import {
  canGoBack,
  NAVIGATION_HISTORY_STORAGE_KEY,
  readNavigationHistory,
  recordNavigation,
  updateCurrentNavigation,
  returnFromEditor,
} from "@/lib/navigation-history";

const storage = window.sessionStorage;

afterEach(() => {
  storage.clear();
});

it("returns to the actual filtered origin and falls back for a direct editor URL", () => {
  const router = { back: vi.fn(), replace: vi.fn() };
  window.history.replaceState({}, "", "/en/corporate/employees/member_1/edit");
  recordNavigation(storage, "/en/corporate/employees?query=Andrey", false, 300);
  recordNavigation(storage, window.location.pathname, false, 0);
  returnFromEditor(router, "/corporate/employees/member_1");
  expect(router.back).toHaveBeenCalledTimes(1);
  expect(router.replace).not.toHaveBeenCalled();
  storage.clear();
  returnFromEditor(router, "/corporate/employees/member_1");
  expect(router.replace).toHaveBeenCalledWith("/en/corporate/employees/member_1");
  window.history.replaceState({}, "", "/");
});

describe("navigation history", () => {
  it("records routes and truncates the forward branch on browser back", () => {
    recordNavigation(storage, "/en/corporate/projects?query=Mobile", false, 240);
    recordNavigation(storage, "/en/corporate/projects/project_1", false, 0);

    expect(recordNavigation(storage, "/en/corporate/projects?query=Mobile", true, 0)).toBe(240);
    expect(readNavigationHistory(storage)).toEqual([
      { href: "/en/corporate/projects?query=Mobile", scrollY: 240 },
    ]);
  });

  it("updates a replaced URL without losing the current scroll state", () => {
    recordNavigation(storage, "/en/corporate/projects", false, 120);
    updateCurrentNavigation(storage, "/en/corporate/projects?query=Mobile");

    expect(canGoBack(storage, "/en/corporate/projects?query=Mobile")).toBe(false);
    expect(readNavigationHistory(storage)).toEqual([
      { href: "/en/corporate/projects?query=Mobile", scrollY: 120 },
    ]);
    expect(storage.getItem(NAVIGATION_HISTORY_STORAGE_KEY)).toContain("Mobile");
  });
});
