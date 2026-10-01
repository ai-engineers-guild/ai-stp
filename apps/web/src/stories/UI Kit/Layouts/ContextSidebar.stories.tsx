import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { Button } from "@/components/atoms/button";
import { ContextRail, ContextSidebar, type RailItem } from "@/components/layouts/context-rail";
import { CORPORATE_NAV_PAGES, resolveCorporateRail } from "@/lib/corporate-navigation";
import { useSessionUiSlice } from "@/lib/stores/session-ui-slice";
import { useUiSlice } from "@/lib/stores/ui-slice";
import { Icon } from "@/theme/icons";
import en from "../../../../messages/en.json";

const pages = CORPORATE_NAV_PAGES.map((page) => page.id);
const labels = en.hub as Record<string, string>;
function items(pathname: string, mainNavigation = false, allowedPages = pages): RailItem[] {
  return resolveCorporateRail(pathname, allowedPages, mainNavigation).entries.map((entry) => ({
    ...entry,
    label: labels[entry.label] ?? entry.label,
    children: entry.children?.map((child) => ({
      ...child,
      label: labels[child.label] ?? child.label,
    })),
  }));
}
function state(collapsed: boolean, signedIn = true) {
  return (Story: () => React.JSX.Element) => {
    useUiSlice.getState().setSidebarCollapsed(collapsed);
    useSessionUiSlice.setState({ signedInHint: signedIn, corporateNavPages: null });
    return <Story />;
  };
}
function SidebarStoryFrame({ children }: { children: React.ReactNode }) {
  const collapsed = useUiSlice((s) => s.sidebarCollapsed);
  const setCollapsed = useUiSlice((s) => s.setSidebarCollapsed);
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-border bg-background flex h-14 items-center gap-3 border-b px-4 pl-16 lg:pl-4">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="hidden size-11 lg:inline-flex"
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          onClick={() => {
            setCollapsed(!collapsed);
          }}
        >
          <Icon name={collapsed ? "chevronRight" : "chevronLeft"} size="md" />
        </Button>
        <img src="/brand/logo-mark-64.png" alt="" width={28} height={28} />
        <span className="text-sm font-medium">ai_stp</span>
      </header>
      <div className="flex min-h-[calc(100dvh-3.5rem)] flex-1">
        {children}
        <main className="min-w-0 flex-1 p-8 lg:p-12">Page content</main>
      </div>
    </div>
  );
}
const meta = {
  title: "UI Kit/Layouts/ContextSidebar",
  component: ContextSidebar,
  tags: ["autodocs"],
  decorators: [
    state(false),
    (Story) => (
      <SidebarStoryFrame>
        <Story />
      </SidebarStoryFrame>
    ),
  ],
  // Browser scenarios own the axe run; overlapping addon runs share one instance.
  globals: { a11y: { manual: true } },
  parameters: {
    layout: "fullscreen",
    a11y: { test: "error" },
    docs: {
      description: {
        component:
          "One shared navigation frame. Expanded desktop uses independent disclosures; collapsed desktop uses one icon per section and keyboard-accessible flyouts. Mobile uses the existing modal Dialog. Corporate authentication and navigation loading are owned by ContextRail, outside this presentation.",
      },
    },
  },
  args: {
    corporate: true,
    pathname: "/corporate/overview",
    scope: "root",
    back: null,
    items: items("/corporate/overview"),
  },
} satisfies Meta<typeof ContextSidebar>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Overview: Story = {};
export const OrganizationDetail: Story = {
  args: {
    pathname: "/corporate/teams/team_1",
    items: items("/corporate/teams/team_1"),
    back: { href: "/corporate/teams", label: "Back to Teams" },
  },
};
export const Collapsed: Story = {
  decorators: [state(true)],
  args: {
    pathname: "/corporate/teams/team_1",
    items: items("/corporate/teams/team_1"),
  },
};
function AdministrationStory() {
  const [mainNavigation, setMainNavigation] = useState(false);
  const pathname = "/corporate/organization/admins/roles";
  return (
    <ContextSidebar
      corporate
      pathname={pathname}
      scope={mainNavigation ? "root" : "administration"}
      items={items(pathname, mainNavigation)}
      back={null}
      onShowMainNavigation={() => {
        setMainNavigation(true);
      }}
      onNavigate={() => {
        setMainNavigation(false);
      }}
    />
  );
}
export const Administration: Story = {
  render: () => <AdministrationStory />,
  args: {
    pathname: "/corporate/organization/admins/roles",
    scope: "administration",
    items: items("/corporate/organization/admins/roles"),
    back: null,
  },
};
export const AdministrationCollapsed: Story = { ...Administration, decorators: [state(true)] };
export const Dark: Story = { ...Administration, globals: { theme: "dark" } };
export const Mobile: Story = {
  ...Administration,
  globals: { viewport: { value: "mobile1", isRotated: false } },
};
export const ShortDesktop: Story = {
  ...Administration,
  parameters: { chromatic: { viewports: [1024] } },
};
export const LongLabels: Story = {
  args: {
    items: items("/corporate/overview").map((item) => ({
      ...item,
      label: `${item.label} — organizational navigation and resource management`,
    })),
  },
};
export const Restricted: Story = {
  args: { items: items("/corporate/overview").filter((item) => item.id === "overview") },
};
export const DeniedAdministration: Story = {
  args: {
    pathname: "/corporate/organization/admins",
    scope: "root",
    items: items("/corporate/organization/admins", false, [
      "overview",
      "catalog",
      "organization",
      "dashboard",
    ]),
  },
};
export const DeniedAdministrationMobile: Story = {
  ...DeniedAdministration,
  globals: { viewport: { value: "mobile1", isRotated: false } },
};
export const SignedOut: Story = {
  decorators: [state(false, false)],
  render: () => <ContextRail corporate docsHref="https://docs.example.test" allowedPages={pages} />,
};
export const LoadingOrUnavailable: Story = {
  render: () => <ContextRail corporate docsHref="https://docs.example.test" />,
};
export const NoOrganizationAccess: Story = {
  render: () => <ContextRail corporate docsHref="https://docs.example.test" allowedPages={[]} />,
};
