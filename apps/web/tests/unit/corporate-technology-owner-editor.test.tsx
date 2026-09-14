import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { corporateMutationAction } from "@/actions/corporate";

const { mutation } = vi.hoisted(() => ({ mutation: vi.fn<typeof corporateMutationAction>() }));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));

import { CorporateTechnologyOwnerEditor } from "@/components/organisms/corporate-technology-owner-editor";

const props = {
  organizationId: "organization_fixture",
  technologyId: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  ownerAccountId: null,
  revision: 0,
  authorizationRevision: 3,
  csrfToken: "csrf_fixture",
  members: [
    { account_id: "account_active", display_name: "Active employee", state: "active" },
    { account_id: "account_suspended", display_name: "Suspended employee", state: "suspended" },
  ],
};

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("corporate technology owner editor", () => {
  it("assigns only active employees through the independent owner endpoint", async () => {
    mutation.mockResolvedValue({ ok: false, message: "Conflict" });
    render(<CorporateTechnologyOwnerEditor {...props} />);

    expect(screen.getByRole("option", { name: "Active employee" })).toBeVisible();
    expect(screen.queryByRole("option", { name: "Suspended employee" })).toBeNull();
    fireEvent.change(screen.getByLabelText("operationalOwner"), {
      target: { value: "account_active" },
    });
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledOnce();
    });

    expect(mutation.mock.calls[0]?.[0]).toMatchObject({
      method: "PUT",
      path: `/v1/corporate/organizations/${props.organizationId}/technologies/${props.technologyId}/owner`,
      body: {
        owner_account_id: "account_active",
        expected_revision: 0,
        authorization_revision: 3,
      },
    });
    await screen.findByText("Conflict");
  });
});
