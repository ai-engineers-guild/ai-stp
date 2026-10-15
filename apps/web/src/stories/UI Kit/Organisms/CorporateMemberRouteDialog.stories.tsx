import type { Meta, StoryObj } from "@storybook/react";
import { CorporateMemberRouteDialog } from "@/components/organisms/corporate-member-route-dialog";
import type { CorporateContext, CorporateMember } from "@/lib/api/generated/types.gen";
export const member: CorporateMember = {
  schema_version: 1,
  account_id: "account_example",
  available_actions: ["member.update"],
  contact_email: null,
  display_name: "Ada Example",
  job_title_id: null,
  job_title_name: null,
  joined_at: null,
  last_activity_at: null,
  revision: 0,
  role: "staff",
  state: "active",
};
export const context: CorporateContext = {
  schema_version: 1,
  organization: {
    schema_version: 1,
    organization_id: "organization_example",
    display_name: "Example",
    authorization_revision: 0,
    state: "active",
  },
  member,
  teams: [],
  projects: [],
  bindings: [],
  capabilities: ["member.update"],
};
const meta = {
  title: "UI Kit/Organisms/CorporateMemberRouteDialog",
  component: CorporateMemberRouteDialog,
  tags: ["autodocs"],
  args: { member, context, roles: [], jobTitles: [], csrfToken: "" },
} satisfies Meta<typeof CorporateMemberRouteDialog>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Edit: Story = {};
