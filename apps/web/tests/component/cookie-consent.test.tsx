import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CookieConsent } from "@/components/organisms/cookie-consent";
import { OPEN_COOKIE_PREFERENCES_EVENT } from "@/components/molecules/cookie-preferences-trigger";

const labels = {
  title: "Cookie choices",
  body: "Optional cookies stay off.",
  necessary: "Necessary",
  analytics: "Analytics",
  marketing: "Marketing",
  accept: "Accept all",
  reject: "Reject optional",
  save: "Save choices",
  manage: "Cookie settings",
  privacy: "Privacy policy",
};
describe("CookieConsent", () => {
  it("rejects optional categories and reopens only from the account settings event", async () => {
    document.cookie = "ai_stp_consent=; Max-Age=0; Path=/";
    const user = userEvent.setup();
    render(<CookieConsent labels={labels} privacyHref="/en/legal/privacy" />);
    expect(await screen.findByRole("dialog", { name: labels.title })).toBeVisible();
    expect(screen.getByRole("dialog", { name: labels.title })).toHaveClass(
      "bottom-4",
      "left-1/2",
      "-translate-x-1/2",
      "w-[calc(100%-2rem)]",
      "max-w-2xl",
    );
    expect(screen.getByRole("link", { name: labels.privacy })).toHaveAttribute(
      "href",
      "/en/legal/privacy",
    );
    await user.click(screen.getByRole("button", { name: labels.reject }));
    expect(document.cookie).toContain("ai_stp_consent=v1.none");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: labels.manage })).not.toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event(OPEN_COOKIE_PREFERENCES_EVENT));
    });
    expect(screen.getByRole("dialog")).toBeVisible();
  });
});
