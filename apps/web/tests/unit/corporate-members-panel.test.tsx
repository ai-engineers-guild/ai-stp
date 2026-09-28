import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { corporateMutationAction } from "@/actions/corporate";
import type { CorporateInvitation } from "@/lib/api/generated/types.gen";

const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
}));

vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import { CorporateMembersPanel } from "@/components/organisms/corporate-members-panel";

const labels = {
  members: "Members",
  noMembers: "No members",
  inviteTitle: "Invite a member",
  inviteBody: "Create a link",
  email: "Email",
  displayName: "Display name",
  role: "Role",
  expiresInDays: "Expires in days",
  create: "Create",
  invite: "Invite",
  creating: "Inviting",
  invitations: "Invitations",
  noInvitations: "No invitations yet.",
  expiresAt: "Expires",
  revoke: "Revoke",
  revoking: "Revoking",
  invitationLinks: "Invitation links",
  copy: "Copy",
  copyAll: "Copy all",
  copied: "Copied",
  bulkImport: "Bulk import",
  bulkImportBody: "Paste recipients",
  importFile: "Import file",
  importText: "Or paste text",
  importPlaceholder: "name@example.com, Jane",
  parse: "Parse",
  parsedCount: "{count} recipients parsed",
  inviteAll: "Invite all",
  bulkProgress: "{done} of {total} invitations created",
  bulkFailed: "Import stopped at a failed invitation.",
  domainPolicy: "Email domain policy",
  domainPolicyBody: "Restrict domains",
  domainRestrict: "Restrict",
  domains: "Domains",
  domainsPlaceholder: "example.com",
  domainsHint: "One per line",
  save: "Save",
  saving: "Saving",
  saved: "Saved",
  failed: "Failed",
  exportFormat: "Format",
  download: "Download",
  mail: "Mail",
  mailQueued: "queued",
  mailSent: "sent",
  mailFailed: "failed",
};

function invitation(overrides: Partial<CorporateInvitation>): CorporateInvitation {
  return {
    schema_version: 1,
    invitation_id: "invite_fixture",
    organization_id: "organization_fixture",
    recipient_email: "user@example.com",
    display_name: "User",
    role: "staff",
    team_ids: [],
    project_ids: [],
    job_title_id: null,
    state: "pending",
    expires_at: "2026-01-01T00:00:00Z",
    created_at: "2025-12-31T00:00:00Z",
    accepted_account_id: null,
    token: null,
    delivery_state: null,
    delivery_error: null,
    ...overrides,
  };
}

function renderPanel(invitations: CorporateInvitation[]) {
  return render(
    <CorporateMembersPanel
      csrfToken="csrf"
      organizationId="organization_fixture"
      authorizationRevision={1}
      locale="en"
      members={[]}
      roles={[]}
      invitations={invitations}
      allowedDomains={[]}
      canInvite
      canManagePolicy={false}
      labels={labels}
    />,
  );
}

describe("CorporateMembersPanel mail delivery", () => {
  it("renders the mail ledger state on each invitation", () => {
    renderPanel([
      invitation({
        invitation_id: "invite_1",
        recipient_email: "a@example.com",
        delivery_state: "sent",
      }),
      invitation({
        invitation_id: "invite_2",
        recipient_email: "b@example.com",
        delivery_state: "queued",
      }),
      invitation({
        invitation_id: "invite_3",
        recipient_email: "c@example.com",
        delivery_state: null,
      }),
    ]);
    expect(screen.getByText("Mail sent")).toBeInTheDocument();
    expect(screen.getByText("Mail queued")).toBeInTheDocument();
    expect(screen.queryAllByText(/Mail failed/)).toHaveLength(0);
  });

  it("shows the provider error when the delivery failed", () => {
    renderPanel([
      invitation({
        delivery_state: "failed",
        delivery_error: "resend: sender domain is not verified",
      }),
    ]);
    expect(screen.getByText("Mail failed")).toBeInTheDocument();
    expect(screen.getByText("Mail: resend: sender domain is not verified")).toBeInTheDocument();
  });
});

describe("CorporateMembersPanel mutation errors", () => {
  it("surfaces a rejected mutation as an alert instead of a quiet note", async () => {
    mutation.mockResolvedValue({ ok: false, message: "email domain is not allowed" });
    renderPanel([invitation({})]);
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("email domain is not allowed"),
    );
    expect(refresh).not.toHaveBeenCalled();
  });

  it("renders a successful mutation as a plain status note", async () => {
    mutation.mockResolvedValue({ ok: true, data: {} });
    renderPanel([invitation({})]);
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });
});
