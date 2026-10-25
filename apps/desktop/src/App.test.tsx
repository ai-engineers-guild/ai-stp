// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import App from "./App";
import { useApp } from "./store";
import { useContexts } from "./contexts";

const originalScrollTo = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  "scrollTo",
);

beforeEach(() => {
  useContexts.setState({
    views: [],
    selected: null,
    result: null,
    loading: false,
    switching: false,
    refresh: vi.fn(async () => {}),
  });
  window.location.hash = "#/";
  Object.defineProperty(HTMLElement.prototype, "scrollTo", {
    configurable: true,
    value: vi.fn(),
  });
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  useApp.setState({
    refreshCli: vi.fn(async () => {}),
    refreshAuth: vi.fn(async () => {}),
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  if (originalScrollTo) {
    Object.defineProperty(HTMLElement.prototype, "scrollTo", originalScrollTo);
  } else {
    Reflect.deleteProperty(HTMLElement.prototype, "scrollTo");
  }
  document.documentElement.classList.remove("dark");
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
  "opens the full shell and changes theme without preference storage: %j",
  (storage) => {
    vi.stubGlobal("localStorage", storage);
    render(<App />);
    expect(screen.getByRole("link", { name: "ai-stp home" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Use light theme" }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  },
);
