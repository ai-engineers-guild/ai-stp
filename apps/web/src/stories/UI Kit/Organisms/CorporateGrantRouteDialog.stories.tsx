import type { Meta, StoryObj } from "@storybook/react";
import { CorporateGrantRouteDialog } from "@/components/organisms/corporate-member-route-dialog";
import { member, context } from "./CorporateMemberRouteDialog.stories";
const meta = {
  title: "UI Kit/Organisms/CorporateGrantRouteDialog",
  component: CorporateGrantRouteDialog,
  args: {
    csrfToken: "",
    organizationId: context.organization.organization_id,
    authorizationRevision: 0,
    members: [member],
    initialMemberIds: [member.account_id],
    roles: [],
    grantableRoleNames: [],
    teams: [],
    projects: [],
    scopeOptions: [],
    definitions: [],
    capabilities: [],
  },
} satisfies Meta<typeof CorporateGrantRouteDialog>;
export default meta;
type Story = StoryObj<typeof meta>;
export const SelectedEmployee: Story = {};
