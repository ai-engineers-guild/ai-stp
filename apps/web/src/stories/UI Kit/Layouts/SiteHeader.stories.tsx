import type { Meta, StoryObj } from "@storybook/react";

import { SiteHeader } from "@/components/layouts/site-header";
import { useSessionUiSlice } from "@/lib/stores/session-ui-slice";

/**
 * The header learns presence from `/api/session` after hydration, so a story
 * primes the same store the fetch would write to. Storybook serves no such
 * route, and the hook leaves the hint alone when the request does not answer
 * — which is exactly what makes priming it here work.
 */
function withSession(signedIn: boolean) {
  return (Story: () => React.JSX.Element) => {
    useSessionUiSlice.setState({ signedInHint: signedIn });
    return <Story />;
  };
}

const meta = {
  title: "UI Kit/Layouts/SiteHeader",
  component: SiteHeader,
  tags: ["autodocs"],
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "Top chrome: nav, locale, theme toggle, Sign in vs Sign out. Presence is asked at request time from `/api/session`, never rendered into static HTML.",
      },
    },
  },
} satisfies Meta<typeof SiteHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Guest: Story = {
  args: { docsHref: "http://localhost:8011" },
  decorators: [withSession(false)],
};

export const SignedIn: Story = {
  args: { docsHref: "http://localhost:8011" },
  decorators: [withSession(true)],
};

export const Mobile360: Story = {
  args: { docsHref: "http://localhost:8011" },
  decorators: [withSession(false)],
  parameters: { viewport: { defaultViewport: "mobile1" }, layout: "fullscreen" },
};

export const Mobile430SignedIn: Story = {
  args: { docsHref: "http://localhost:8011" },
  decorators: [withSession(true)],
  parameters: {
    viewport: { defaultViewport: "mobile2" },
    layout: "fullscreen",
    chromatic: { viewports: [360, 430] },
  },
};
