import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import {
  createDirectGrantAction,
  createInvitationAction,
  revokeGrantAction,
} from "@/actions/grants";
import { AccessWorkspace } from "@/components/organisms/access-workspace";

const refresh = vi.fn();
const idempotencyKey = "88abdcde-5013-40ae-a319-bcd11b0a07fb";

vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh }),
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={`/en${href}`}>{children}</a>
  ),
}));

vi.mock("@/actions/grants", () => ({
  createDirectGrantAction: vi.fn(() => Promise.resolve({ operationId: "op_direct" })),
  createInvitationAction: vi.fn(() => Promise.resolve({ operationId: "op_invite" })),
  revokeGrantAction: vi.fn(() => Promise.resolve({ operationId: "op_revoke" })),
  revokeInvitationAction: vi.fn(),
}));

vi.mock("@/components/organisms/contact-report-dialog", () => ({
  ContactReportDialog: () => null,
}));

const labels = {
  create: "Create access",
  email: "Email",
  stableId: "Stable ID",
  kind: "Kind",
  recipientKind: "Recipient identifier",
  githubUsername: "GitHub username",
  userId: "User ID",
  kindComponent: "component",
  kindSetup: "setup",
  peopleWithAccess: "People with access",
  emptyPeople: "No one has access",
  revoke: "Revoke",
  revokeWarning: "Confirm revoke",
  revokeTitle: "Revoke access?",
  cancel: "Cancel",
  confirm: "Revoke access",
  revoking: "Revoking…",
  copyId: "Copy ID",
  copied: "Copied",
  report: "Report user",
  more: "More actions",
  user: "User",
  referenceId: "Reference ID",
};

describe("AccessWorkspace direct grants", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(crypto, "randomUUID").mockReturnValue(idempotencyKey);
  });

  it.each([
    ["github_username", "GitHub username", "octocat", undefined],
    ["user_id", "User ID", "account_01JQZK7B8N4M6P2R9T5V0X3Y70", undefined],
    ["github_username", "GitHub username", " @OctoCat ", 2],
    ["user_id", "User ID", "account_01JQZK7B8N4M6P2R9T5V0X3Y70", 2],
  ] as const)(
    "submits a %s recipient as a direct grant",
    async (recipientKind, label, recipient, revision) => {
      const user = userEvent.setup();
      render(
        <AccessWorkspace
          users={[]}
          csrfToken="csrf"
          labels={labels}
          observedGrants={
            revision === undefined
              ? []
              : [
                  {
                    schema_version: 1,
                    grant_id: "grant_01",
                    revision,
                    object_kind: "component",
                    stable_id: "component_test",
                    major: 1,
                    grantee_account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y70",
                    owner_account_id: "account_owner",
                    state: "revoked",
                    created_at: "2026-10-13T00:00:00Z",
                    revoked_at: "2026-10-13T01:00:00Z",
                    recipient_kind: "github_username",
                    recipient: "octocat",
                  },
                ]
          }
        />,
      );

      await user.selectOptions(screen.getByLabelText("Recipient identifier"), recipientKind);
      await user.type(screen.getByLabelText(label), recipient);
      await user.type(screen.getByLabelText("Stable ID"), "component_test");
      await user.click(screen.getByRole("button", { name: "Create access" }));

      await waitFor(() => {
        expect(createDirectGrantAction).toHaveBeenCalledWith({
          csrfToken: "csrf",
          objectKind: "component",
          stableId: "component_test",
          major: 1,
          recipientKind,
          recipient,
          expectedGrantId: revision === undefined ? undefined : "grant_01",
          expectedRevision: revision,
          idempotencyKey,
        });
      });
      expect(createInvitationAction).not.toHaveBeenCalled();
      expect(refresh).toHaveBeenCalled();
    },
  );

  it("shows a user card and keeps user actions in the menu", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    const workspace = (revision: number) => (
      <AccessWorkspace
        users={[
          {
            grantId: "grant_01",
            revision,
            accountId: "account_01",
            displayName: "Ada Lovelace",
            avatarUrl: null,
          },
        ]}
        csrfToken="csrf"
        labels={labels}
      />
    );
    const { rerender } = render(workspace(7));

    expect(screen.getByRole("link", { name: /Ada Lovelace/ })).toHaveAttribute(
      "href",
      "/en/publishers/account_01",
    );
    await user.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Revoke",
      "Copy ID",
      "Report user",
    ]);
    await user.click(screen.getByRole("menuitem", { name: "Copy ID" }));
    expect(writeText).toHaveBeenCalledWith("account_01");
    await user.click(screen.getByRole("button", { name: "More actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Revoke" }));
    // A refresh while the confirmation is open cannot widen the approved intent.
    rerender(workspace(9));
    await user.click(screen.getByRole("button", { name: "Revoke access" }));
    await waitFor(() => {
      expect(revokeGrantAction).toHaveBeenCalledWith({
        csrfToken: "csrf",
        grantId: "grant_01",
        reason: "",
        expectedRevision: 7,
        idempotencyKey,
      });
    });
    expect(confirmSpy).not.toHaveBeenCalled();
  });
});
