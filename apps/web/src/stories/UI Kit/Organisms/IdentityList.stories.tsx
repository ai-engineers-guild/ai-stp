import type { Meta, StoryObj } from "@storybook/react";

import { IdentityList } from "@/components/organisms/identity-list";
import type { LinkedIdentity } from "@/lib/api/generated/types.gen";
import { FIXTURE_TIMESTAMP } from "@/mocks/fixtures/identity";

const githubOnly: LinkedIdentity[] = [
  {
    provider: "github",
    linked_at: FIXTURE_TIMESTAMP,
    avatar_url: "https://avatars.githubusercontent.com/u/1?v=4",
    display_name: "fixture-github",
  },
];

const bothProviders: LinkedIdentity[] = [
  {
    provider: "github",
    linked_at: FIXTURE_TIMESTAMP,
    avatar_url: "https://avatars.githubusercontent.com/u/1?v=4",
    display_name: "fixture-github",
  },
  {
    provider: "google",
    linked_at: FIXTURE_TIMESTAMP,
    avatar_url: null,
    display_name: "fixture.google@example.com",
  },
];

const meta = {
  title: "UI Kit/Organisms/IdentityList",
  component: IdentityList,
  tags: ["autodocs"],
  args: {
    csrfToken: "storybook-csrf-token",
    returnTo: "/en/account",
    identities: githubOnly,
  },
  parameters: {
    docs: {
      description: {
        component:
          "Linked OAuth identities (GitHub / Google): avatar, provider badge, unlink, and link-another actions.",
      },
    },
  },
} satisfies Meta<typeof IdentityList>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Single linked identity — unlink disabled (last identity rule). */
export const GitHubOnly: Story = {
  args: { identities: githubOnly },
};

/** Both providers linked — unlink enabled; no “link another” row. */
export const GitHubAndGoogle: Story = {
  args: { identities: bothProviders },
};

/** Google only — shows “Link GitHub” secondary action. */
export const GoogleOnly: Story = {
  args: {
    identities: [
      {
        provider: "google",
        linked_at: FIXTURE_TIMESTAMP,
        avatar_url: null,
        display_name: "Ada G.",
      },
    ],
  },
};
