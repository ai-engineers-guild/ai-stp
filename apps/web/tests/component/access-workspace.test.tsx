import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createDirectGrantAction, createInvitationAction } from "@/actions/grants";
import { AccessWorkspace } from "@/components/organisms/access-workspace";

const refresh = vi.fn();

vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh }),
}));

vi.mock("@/actions/grants", () => ({
  createDirectGrantAction: vi.fn(() => Promise.resolve({ operationId: "op_direct" })),
  createInvitationAction: vi.fn(() => Promise.resolve({ operationId: "op_invite" })),
  revokeGrantAction: vi.fn(),
  revokeInvitationAction: vi.fn(),
}));

const labels = {
  invitations: "Invitations",
  grants: "Grants",
  emptyInvitations: "No invitations",
  emptyGrants: "No grants",
  create: "Create access",
  email: "Email",
  major: "Major",
  stableId: "Stable ID",
  kind: "Kind",
  recipientKind: "Recipient identifier",
  githubUsername: "GitHub username",
  userId: "User ID",
  kindComponent: "component",
  kindSetup: "setup",
  revoke: "Revoke",
  revokeWarning: "Confirm revoke",
  reason: "Reason",
  confirm: "Confirm",
  cancel: "Cancel",
  referenceId: "Reference ID",
};

describe("AccessWorkspace direct grants", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each([
    ["github_username", "GitHub username", "octocat"],
    ["user_id", "User ID", "account_01JQZK7B8N4M6P2R9T5V0X3Y70"],
  ] as const)(
    "submits a %s recipient as a direct grant",
    async (recipientKind, label, recipient) => {
      const user = userEvent.setup();
      render(<AccessWorkspace invitations={[]} grants={[]} csrfToken="csrf" labels={labels} />);

      await user.selectOptions(screen.getByLabelText("Recipient identifier"), recipientKind);
      await user.type(screen.getByLabelText(label), recipient);
      await user.type(screen.getByLabelText("Stable ID"), "component_test");
      await user.clear(screen.getByLabelText("Major"));
      await user.type(screen.getByLabelText("Major"), "2");
      await user.click(screen.getByRole("button", { name: "Create access" }));

      await waitFor(() => {
        expect(createDirectGrantAction).toHaveBeenCalledWith({
          csrfToken: "csrf",
          objectKind: "component",
          stableId: "component_test",
          major: 2,
          recipientKind,
          recipient,
        });
      });
      expect(createInvitationAction).not.toHaveBeenCalled();
      expect(refresh).toHaveBeenCalled();
    },
  );
});
