import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@next/third-parties/google", () => ({
  GoogleAnalytics: ({ gaId }: { gaId: string }) => <div data-testid="ga" data-ga-id={gaId} />,
}));

const { ConsentedAnalytics } = await import("@/components/organisms/consented-analytics");

describe("ConsentedAnalytics", () => {
  afterEach(() => {
    document.cookie = "ai_stp_consent=; Max-Age=0; Path=/";
  });

  it("loads official trackers only after analytics consent", async () => {
    document.cookie = "ai_stp_consent=v1.all; Path=/";
    render(<ConsentedAnalytics gaMeasurementId="G-TEST" yandexCounterId="12345678" />);
    await waitFor(() => {
      expect(screen.getByTestId("ga")).toHaveAttribute("data-ga-id", "G-TEST");
    });
    expect(document.querySelector('[data-analytics="yandex-metrika"]')).toHaveAttribute(
      "data-counter",
      "12345678",
    );
  });

  it("stays unloaded after decline and when measurement ids are empty", async () => {
    document.cookie = "ai_stp_consent=v1.none; Path=/";
    const declined = render(
      <ConsentedAnalytics gaMeasurementId="G-TEST" yandexCounterId="12345678" />,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByTestId("ga")).not.toBeInTheDocument();
    expect(document.querySelector('[data-analytics="yandex-metrika"]')).toBeNull();
    declined.unmount();

    document.cookie = "ai_stp_consent=v1.all; Path=/";
    render(<ConsentedAnalytics gaMeasurementId="" yandexCounterId="" />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByTestId("ga")).not.toBeInTheDocument();
    expect(document.querySelector('[data-analytics="yandex-metrika"]')).toBeNull();
  });

  it("unloads trackers when analytics consent is withdrawn later", async () => {
    document.cookie = "ai_stp_consent=v1.all; Path=/";
    render(<ConsentedAnalytics gaMeasurementId="G-TEST" yandexCounterId="12345678" />);
    await waitFor(() => {
      expect(screen.getByTestId("ga")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(
        document.querySelector(`script[src="https://mc.yandex.ru/metrika/tag.js"]`),
      ).not.toBeNull();
    });
    act(() => {
      window.dispatchEvent(
        new CustomEvent("ai-stp-consent", { detail: { analytics: false, marketing: false } }),
      );
    });
    expect(screen.queryByTestId("ga")).not.toBeInTheDocument();
    expect(document.querySelector('[data-analytics="yandex-metrika"]')).toBeNull();
    expect(document.querySelector(`script[src="https://mc.yandex.ru/metrika/tag.js"]`)).toBeNull();
  });
});
