import type { Meta, StoryObj } from "@storybook/react";

import { SiteHeader } from "@/components/layouts/site-header";

const meta = {
  title: "UI Kit/Layouts/SiteHeader",
  component: SiteHeader,
  tags: ["autodocs"],
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "Top chrome: nav, locale, theme toggle, Sign in vs Sign out. `signedIn` is server-truth.",
      },
    },
  },
} satisfies Meta<typeof SiteHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Guest: Story = {
  args: { signedIn: false, docsHref: "http://localhost:8011" },
};

export const SignedIn: Story = {
  args: { signedIn: true, docsHref: "http://localhost:8011" },
};

export const Mobile360: Story = {
  args: { signedIn: false, docsHref: "http://localhost:8011" },
  parameters: { viewport: { defaultViewport: "mobile1" }, layout: "fullscreen" },
};

export const Mobile430SignedIn: Story = {
  args: { signedIn: true, docsHref: "http://localhost:8011" },
  parameters: {
    viewport: { defaultViewport: "mobile2" },
    layout: "fullscreen",
    chromatic: { viewports: [360, 430] },
  },
};
