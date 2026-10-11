import type { ReactNode } from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const route = vi.hoisted(() => ({ path: "/" }));
vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string) => key,
}));
vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));
vi.mock("@/lib/use-hydrated", () => ({ useHydrated: () => true }));
vi.mock("@/lib/features/compiled", () => ({
  COMPILED_FEATURE_PROFILE: "saas",
  COMPILED_FEATURES: {
    content_hub: true,
    saas_public_pages: true,
    catalog_usage_metrics: true,
  },
}));
vi.mock("@/lib/i18n/navigation", () => ({
  usePathname: () => route.path,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
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

import { SiteHeader } from "@/components/layouts/site-header";
import { useSessionUiSlice } from "@/lib/stores/session-ui-slice";
import { useUiSlice } from "@/lib/stores/ui-slice";

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
});

afterEach(() => {
  cleanup();
  route.path = "/";
  useUiSlice.setState({ sidebarCollapsed: false });
  useSessionUiSlice.setState({ signedInHint: false, corporateNavPages: null });
  vi.unstubAllGlobals();
});

it("omits the rail collapse control only on the SaaS landing page", () => {
  render(<SiteHeader docsHref="https://docs.test" />);
  expect(document.querySelector('[data-ui="nav-collapse"]')).toBeNull();
});
