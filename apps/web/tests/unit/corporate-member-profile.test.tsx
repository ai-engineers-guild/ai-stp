import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { corporateMutationAction } from "@/actions/corporate";
const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
}));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({ useRouter: () => ({ refresh }) }));
import { CorporateMemberProfile } from "@/components/organisms/corporate-member-profile";
const props = {
  organizationId: "organization_fixture",
  authorizationRevision: 3,
  csrfToken: "csrf_fixture",
  member: {
    schema_version: 1 as const,
    account_id: "account_fixture",
    display_name: "Alice",
    role: "staff",
    state: "active" as const,
    revision: 4,
  },
};
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("edits only the tenant name and preserves a transport-failed draft and retry key", async () => {
  mutation.mockRejectedValueOnce(new Error("connection lost"));
  mutation.mockResolvedValueOnce({ ok: false, message: "Conflict" });
  render(<CorporateMemberProfile {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "edit" }));
  expect(screen.queryByLabelText("role")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("displayName"), { target: { value: "Mobile lead" } });
  fireEvent.click(screen.getByRole("button", { name: "update" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("displayName")).toHaveValue("Mobile lead");
  fireEvent.click(screen.getByRole("button", { name: "update" }));
  await screen.findByText("Conflict");
  const first = mutation.mock.calls[0]?.[0];
  expect(first?.path).toBe(
    "/v1/corporate/organizations/organization_fixture/members/account_fixture/profile",
  );
  expect(first?.body).toMatchObject({
    display_name: "Mobile lead",
    expected_revision: 4,
    authorization_revision: 3,
  });
  expect(first?.body).not.toHaveProperty("role");
  expect(mutation.mock.calls[1]?.[0].body).toEqual(first?.body);
  expect(refresh).not.toHaveBeenCalled();
});

it("discards a cancelled draft and refuses a blank name", () => {
  render(<CorporateMemberProfile {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "edit" }));
  fireEvent.change(screen.getByLabelText("displayName"), { target: { value: " " } });
  expect(screen.getByRole("button", { name: "update" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "cancel" }));
  fireEvent.click(screen.getByRole("button", { name: "edit" }));
  expect(screen.getByLabelText("displayName")).toHaveValue("Alice");
});
