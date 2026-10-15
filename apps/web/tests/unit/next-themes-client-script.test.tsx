import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ThemeProvider } from "next-themes";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("renders theme content without creating a client script tag", () => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  );
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  render(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <div>Theme content</div>
    </ThemeProvider>,
  );
  expect(screen.getByText("Theme content")).toBeInTheDocument();
  expect(document.body.querySelector("script")).toBeNull();
  expect(error.mock.calls.flat().join(" ")).not.toContain(
    "Encountered a script tag while rendering React component",
  );
});
