import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  back: vi.fn(),
  push: vi.fn(),
  canGoBack: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: mocks.back, push: mocks.push }),
  usePathname: () => "/en/current",
}));
vi.mock("@/lib/navigation-history", () => ({
  canGoBack: mocks.canGoBack,
  currentNavigationHref: () => "/en/from",
  getNavigationStorage: () => window.sessionStorage,
}));

const { HistoryBackButton } = await import("@/components/molecules/history-back-button");

afterEach(() => {
  vi.clearAllMocks();
});

describe("HistoryBackButton", () => {
  it("uses the recorded browser stack and keeps the kit button contract", async () => {
    mocks.canGoBack.mockReturnValue(true);
    const user = userEvent.setup();
    render(<HistoryBackButton label="Back" fallback="/en/fallback" />);

    const button = screen.getByRole("button", { name: "Back" });
    expect(button).toHaveAttribute("data-ui", "nav-back");
    expect(button).toHaveClass("min-h-11", "rounded-sm");
    await user.click(button);
    expect(mocks.back).toHaveBeenCalledOnce();
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("uses the localized fallback when there is no in-app history", async () => {
    mocks.canGoBack.mockReturnValue(false);
    const user = userEvent.setup();
    render(<HistoryBackButton label="Back" fallback="/fallback" />);

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(mocks.push).toHaveBeenCalledWith("/en/fallback");
    expect(mocks.back).not.toHaveBeenCalled();
  });
});
