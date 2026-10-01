import type { ReactNode } from "react";
import { act } from "react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { expect, it, vi } from "vitest";
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({
  usePathname: () => "/corporate/overview",
  Link: ({
    href,
    children,
    prefetch,
    ...props
  }: {
    href: string;
    children: ReactNode;
    prefetch?: boolean;
  }) => {
    void prefetch;
    return (
      <a href={href} {...props}>
        {children}
      </a>
    );
  },
}));
import { ContextRail, ContextSidebar } from "@/components/layouts/context-rail";
import { useUiSlice } from "@/lib/stores/ui-slice";
import { useSessionUiSlice } from "@/lib/stores/session-ui-slice";

it("hydrates static HTML without mismatches with a saved collapsed preference and authenticated client", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  const errors: unknown[] = [];
  const consoleError = vi.spyOn(console, "error").mockImplementation((error) => errors.push(error));
  sessionStorage.setItem("ai-stp-sidebar-collapsed", "true");
  useUiSlice.setState({ sidebarCollapsed: true });
  useSessionUiSlice.setState({ signedInHint: true });
  const frames = [
    <ContextRail
      key="corporate"
      corporate
      docsHref="/docs"
      allowedPages={["overview"]}
      serverAuthorized
    />,
    <ContextSidebar
      key="public"
      corporate={false}
      pathname="/"
      scope="saas"
      back={null}
      items={[{ id: "home", label: "Home", href: "/", icon: "cards", active: true }]}
    />,
  ];
  try {
    for (const frame of frames) {
      const container = document.createElement("div");
      document.body.append(container);
      container.innerHTML = renderToString(frame);
      expect(container.querySelector('[data-ui="context-sidebar"]')).not.toBeNull();
      let root!: ReturnType<typeof hydrateRoot>;
      await act(async () => {
        root = hydrateRoot(container, frame, { onRecoverableError: (error) => errors.push(error) });
        await Promise.resolve();
      });
      expect(container.querySelector("aside")).toHaveAttribute("data-collapsed", "true");
      await act(async () => {
        root.unmount();
        await Promise.resolve();
      });
      container.remove();
    }
    expect(errors).toEqual([]);
  } finally {
    consoleError.mockRestore();
    vi.unstubAllGlobals();
    sessionStorage.clear();
    useUiSlice.setState({ sidebarCollapsed: false });
    useSessionUiSlice.setState({ signedInHint: false, corporateNavPages: null });
  }
});
