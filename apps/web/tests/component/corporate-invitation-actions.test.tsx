import { NextIntlClientProvider } from "next-intl";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import en from "../../messages/en.json";
import { CorporateInvitationsPanel } from "@/components/organisms/corporate-invitations-panel";
import { corporateHandlers } from "@/lib/api/mock-corporate";
import fixture from "@/mocks/corporate-overview-fixture";
import type { CorporateContext, CorporateRoleList } from "@/lib/api/generated/types.gen";

const actions = vi.hoisted(() => ({ mutate: vi.fn(), refresh: vi.fn() }));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: actions.mutate }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ refresh: actions.refresh }),
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
  usePathname: () => "/corporate/organization/admins",
  useRouter: () => ({ replace: vi.fn() }),
}));
const fixtureCase = (
  fixture as { cases: { body: { organization: { organization_id: string } } }[] }
).cases[0];
if (!fixtureCase) throw new Error("Missing fixture");
const base = `/v1/corporate/organizations/${fixtureCase.body.organization.organization_id}`;
const context = corporateHandlers("GET", `${base}/context`, true, null)?.body as CorporateContext;
const roles = (corporateHandlers("GET", `${base}/roles`, true, null)?.body as CorporateRoleList)
  .items;

it("recovers immediately from denial, explains unavailable roles and reuses the retry key", async () => {
  const user = userEvent.setup();
  actions.refresh.mockClear();
  let resolve!: (value: unknown) => void;
  actions.mutate.mockReturnValueOnce(
    new Promise((done) => {
      resolve = done;
    }),
  );
  actions.mutate.mockResolvedValue({
    ok: false,
    code: "AI_STP_PERMISSION_DENIED",
    message: "grant exceeds delegated authority",
  });
  render(
    <NextIntlClientProvider locale="en" messages={en}>
      <CorporateInvitationsPanel
        csrfToken="fixture"
        context={context}
        roles={roles}
        grantableRoles={["staff"]}
        members={[]}
        invitations={[]}
        now="2026-10-01T00:00:00Z"
      />
    </NextIntlClientProvider>,
  );
  await user.click(screen.getByRole("button", { name: "Invite member" }));
  await user.type(screen.getByRole("textbox", { name: "Email" }), "recipient@example.com");
  const select = screen.getByRole("combobox", { name: "Role" });
  expect(screen.getByRole("option", { name: "superadmin — unavailable" })).toBeDisabled();
  expect(select).toHaveAccessibleDescription(/permissions you cannot grant/);
  await user.selectOptions(select, "staff");
  await user.click(screen.getByRole("button", { name: "Send invitation" }));
  expect(screen.getByRole("button", { name: /Sending/ })).toBeDisabled();
  resolve({
    ok: false,
    code: "AI_STP_PERMISSION_DENIED",
    message: "grant exceeds delegated authority",
  });
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Send invitation" })).toBeEnabled(),
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Your current permissions");
  expect(actions.refresh).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Send invitation" }));
  await waitFor(() => {
    expect(actions.mutate).toHaveBeenCalledTimes(2);
  });
  const first = actions.mutate.mock.calls[0]?.[0] as { body: { idempotency_key: string } };
  const second = actions.mutate.mock.calls[1]?.[0] as { body: { idempotency_key: string } };
  expect(first.body.idempotency_key).toEqual(second.body.idempotency_key);
});

it("offers delegated roles when the inviter cannot read the role catalog", async () => {
  const user = userEvent.setup();
  render(
    <NextIntlClientProvider locale="en" messages={en}>
      <CorporateInvitationsPanel
        csrfToken="fixture"
        context={{ ...context, capabilities: ["member.invite"] }}
        roles={[]}
        grantableRoles={["staff"]}
        members={[]}
        invitations={[]}
        now="2026-10-01T00:00:00Z"
      />
    </NextIntlClientProvider>,
  );
  await user.click(screen.getByRole("button", { name: "Invite member" }));
  expect(screen.getByRole("option", { name: "staff" })).toBeEnabled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
