import type { Meta, StoryObj } from "@storybook/react";

import { ProfileForm } from "@/components/organisms/profile-form";

const initial = {
  schema_version: 1,
  account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  state: "draft",
  draft: {
    revision_id: "prevision_story",
    content_digest: "sha256:story",
    fields: {
      display_name: "Story Author",
      bio: "Short bio",
      links: [{ label: "GitHub", url: "https://github.com/example" }],
      avatar_asset_id: null,
    },
    avatar_url: null,
  },
  published: null,
};

const meta = {
  title: "UI Kit/Organisms/ProfileForm",
  component: ProfileForm,
  tags: ["autodocs"],
  args: {
    initial,
    sessionToken: "mock-session",
  },
  parameters: {
    docs: {
      description: {
        component: "Public profile editor: draft, publish, avatar (SPEC-028).",
      },
    },
  },
} satisfies Meta<typeof ProfileForm>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Draft: Story = {};

export const Mobile360: Story = {
  parameters: { viewport: { defaultViewport: "mobile1" } },
};

export const Mobile430: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile2" },
    chromatic: { viewports: [360, 430] },
  },
};
