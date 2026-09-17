import type { Meta, StoryObj } from "@storybook/react";

import { NavigationTabs } from "@/components/molecules/navigation-tabs";

const organizationTabs = [
  { key: "projects", href: "/corporate/projects", label: "Projects", active: true },
  { key: "teams", href: "/corporate/teams", label: "Teams", active: false },
  { key: "employees", href: "/corporate/members", label: "Employees", active: false },
  {
    key: "technologies",
    href: "/corporate/technologies",
    label: "Technologies",
    active: false,
  },
] as const;

const meta = {
  title: "UI Kit/Molecules/NavigationTabs",
  component: NavigationTabs,
  tags: ["autodocs"],
  args: {
    ariaLabel: "Organization",
    items: organizationTabs,
    variant: "secondary",
  },
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof NavigationTabs>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Secondary: Story = {};

export const Primary: Story = {
  args: {
    ariaLabel: "Primary navigation",
    variant: "primary",
    items: [
      { key: "overview", href: "/corporate/overview", label: "Overview", active: false },
      { key: "catalog", href: "/catalog", label: "Catalog", active: false },
      { key: "organization", href: "/corporate/organization", label: "Organization", active: true },
      {
        key: "landscape",
        href: "/corporate/technology-landscape",
        label: "Landscape",
        active: false,
      },
      { key: "dashboard", href: "/corporate/dashboard", label: "Dashboard", active: false },
      { key: "admins", href: "/corporate/organization/admins", label: "For Admins", active: false },
    ],
  },
};
