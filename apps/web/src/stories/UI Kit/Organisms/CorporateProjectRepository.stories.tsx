import type { Meta, StoryObj } from "@storybook/react";
import { NextIntlClientProvider } from "next-intl";
import en from "../../../../messages/en.json";
import { CorporateProjectRepository } from "@/components/organisms/corporate-project-repository";
const meta = {
  title: "UI Kit/Organisms/CorporateProjectRepository",
  component: CorporateProjectRepository,
  decorators: [
    (Story) => (
      <NextIntlClientProvider locale="en" messages={en}>
        <div className="max-w-sm">
          <Story />
        </div>
      </NextIntlClientProvider>
    ),
  ],
  args: {
    organizationId: "organization_test",
    authorizationRevision: 1,
    csrfToken: "story",
    canManage: true,
    project: {
      schema_version: 1,
      project_id: "remote_project_test",
      organization_id: "organization_test",
      name: "Project",
      state: "active",
      revision: 1,
      repositories: [],
      available_actions: [],
    },
  },
} satisfies Meta<typeof CorporateProjectRepository>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Unlinked: Story = {};
export const Linked: Story = {
  args: {
    project: {
      ...meta.args.project,
      repositories: [
        {
          provider_project_id: "provider",
          provider: "github",
          namespace: "owner/repository",
          repository_url: "https://github.com/owner/repository",
          default_branch: "main",
          observed_at: null,
          observed_revision: null,
        },
      ],
    },
  },
};
export const ReadOnly: Story = { args: { canManage: false } };
