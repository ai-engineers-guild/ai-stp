import { useState } from "react";
import { NextIntlClientProvider } from "next-intl";
import ru from "../../../../messages/ru.json";
import type { Meta, StoryObj } from "@storybook/react";
import { CorporateMembersTable } from "@/components/organisms/corporate-members-table";
import { CorporateMembersDirectory } from "@/components/organisms/corporate-members-directory";
import { CorporateInvitationsPanel } from "@/components/organisms/corporate-invitations-panel";
import { CorporateInviteDialog } from "@/components/organisms/corporate-invite-dialog";
import { corporateHandlers } from "@/lib/api/mock-corporate";
import type {
  CorporateContext,
  CorporateMemberList,
  CorporateInvitationList,
  CorporateRoleList,
} from "@/lib/api/generated/types.gen";
import fixture from "@/mocks/corporate-overview-fixture";

const organizationId = fixture.cases[0]!.body.organization.organization_id;
const base = `/v1/corporate/organizations/${organizationId}`;
const context = corporateHandlers("GET", `${base}/context`, true, null)!.body as CorporateContext;
const members = (
  corporateHandlers("GET", `${base}/members`, true, null)!.body as CorporateMemberList
).items;
const roles = (corporateHandlers("GET", `${base}/roles`, true, null)!.body as CorporateRoleList)
  .items;
const invitations = (
  corporateHandlers("GET", `${base}/invitations`, true, null)!.body as CorporateInvitationList
).items;
const now = "2026-10-01T10:00:00Z";
const meta = {
  title: "UI Kit/Organisms/CorporatePeople",
  component: CorporateMembersDirectory,
  tags: ["autodocs"],
  globals: { a11y: { manual: true } },
  parameters: { layout: "fullscreen", a11y: { test: "error" } },
  decorators: [
    (Story) => (
      <div className="bg-background text-foreground min-h-dvh p-4 sm:p-8">
        <Story />
      </div>
    ),
  ],
  args: { members, roles, context, csrfToken: "storybook-fixture", jobTitles: [], now },
} satisfies Meta<typeof CorporateMembersDirectory>;
export default meta;
type Story = StoryObj<typeof meta>;
export const Members: Story = {};
export const Dark: Story = { globals: { theme: "dark" } };
export const Empty: Story = { args: { members: [] } };
export const ReadOnly: Story = {
  args: { context: { ...context, capabilities: ["member.list", "member.read"] } },
};
export const Mobile: Story = { globals: { viewport: { value: "mobile1", isRotated: false } } };
export const Invitations: Story = {
  render: () => (
    <CorporateInvitationsPanel
      context={context}
      members={members}
      roles={roles}
      invitations={invitations}
      csrfToken="storybook-fixture"
      now={now}
    />
  ),
};
export const Unavailable: Story = {
  render: () => (
    <CorporateInvitationsPanel
      context={context}
      members={members}
      roles={roles}
      invitations={[]}
      csrfToken="storybook-fixture"
      now={now}
      unavailable
    />
  ),
};
function InviteStory({
  busy = false,
  error = null,
  grantableRoles,
}: {
  busy?: boolean;
  error?: string | null;
  grantableRoles?: readonly string[] | null;
}) {
  const [open, setOpen] = useState(true);
  return (
    <CorporateInviteDialog
      open={open}
      onOpenChange={setOpen}
      busy={busy}
      error={error}
      roles={roles.map((role) => role.name)}
      grantableRoles={grantableRoles}
      teams={context.teams.map((team) => ({ value: team.team_id, label: team.name }))}
      submit={() => {
        setOpen(false);
      }}
    />
  );
}
export const Invite: Story = { render: () => <InviteStory /> };
export const InviteError: Story = {
  render: () => <InviteStory error="Access changed. Refresh the page and try again." />,
};
export const InviteBusy: Story = { render: () => <InviteStory busy /> };
export const InviteRestricted: Story = {
  render: () => <InviteStory grantableRoles={["superadmin"]} />,
};
export const InviteNoAuthority: Story = {
  render: () => <InviteStory grantableRoles={[]} />,
};
export const InviteRolesUnavailable: Story = {
  render: () => <InviteStory grantableRoles={null} />,
};
export const InviteRestrictedRussian: Story = {
  render: () => <InviteStory grantableRoles={["superadmin"]} />,
  globals: { theme: "dark" },
  decorators: [
    (Story) => (
      <NextIntlClientProvider locale="ru" messages={ru}>
        <Story />
      </NextIntlClientProvider>
    ),
  ],
};
export const BulkImport: Story = {
  render: () => <InviteStory />,
  play: async () => {
    document.querySelector<HTMLButtonElement>('button[type="button"].border-l')?.click();
  },
};

function TableStory({ empty = false, checked = false }: { empty?: boolean; checked?: boolean }) {
  const [selected, setSelected] = useState<string[]>(checked ? [members[0]!.account_id] : []);
  return (
    <CorporateMembersTable
      rows={empty ? [] : members.slice(0, 10)}
      context={context}
      selected={selected}
      setSelected={setSelected}
      now={now}
      sort="joined_desc"
      update={() => {}}
      empty={empty}
    />
  );
}
export const Table: Story = { render: () => <TableStory /> };
export const TableEmpty: Story = { render: () => <TableStory empty /> };
export const TableSelected: Story = { render: () => <TableStory checked /> };
export const TableMobile: Story = {
  render: () => <TableStory />,
  globals: { viewport: { value: "mobile1", isRotated: false } },
};
