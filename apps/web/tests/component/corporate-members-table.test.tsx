import { NextIntlClientProvider } from "next-intl";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import en from "../../messages/en.json";
import { CorporateMembersTable } from "@/components/organisms/corporate-members-table";
import { corporateHandlers } from "@/lib/api/mock-corporate";
import fixture from "@/mocks/corporate-overview-fixture";
import type { CorporateContext, CorporateMemberList } from "@/lib/api/generated/types.gen";

vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
const fixtureCase = (
  fixture as { cases: { body: { organization: { organization_id: string } } }[] }
).cases[0];
if (!fixtureCase) throw new Error("Missing fixture");
const base = `/v1/corporate/organizations/${fixtureCase.body.organization.organization_id}`;
const context = corporateHandlers("GET", `${base}/context`, true, null)?.body as CorporateContext;
const members = (
  corporateHandlers("GET", `${base}/members`, true, null)?.body as CorporateMemberList
).items;
const props = {
  context,
  selected: [],
  setSelected: vi.fn(),
  now: "2026-10-01T00:00:00Z",
  sort: "joined_desc",
  update: vi.fn(),
  empty: false,
};
it("reuses the table independently, linking roles and teams and keeping row menus nonmodal", async () => {
  const user = userEvent.setup();
  const team = context.teams[0];
  if (!team) throw new Error("Missing team fixture");
  const member = members.find((row) =>
    team.members.some((entry) => entry.account_id === row.account_id),
  );
  if (!member) throw new Error("Missing member fixture");
  render(
    <NextIntlClientProvider locale="en" messages={en}>
      <CorporateMembersTable {...props} rows={[member]} />
    </NextIntlClientProvider>,
  );
  expect(screen.getByRole("link", { name: member.role })).toHaveAttribute(
    "href",
    `/corporate/organization/admins/roles?role=${member.role}`,
  );
  expect(screen.getByRole("link", { name: team.name })).toHaveAttribute(
    "href",
    `/corporate/teams/${team.team_id}`,
  );
  await user.click(screen.getByRole("button", { name: /Actions for/ }));
  expect(screen.getByRole("menuitem", { name: "View profile" })).toBeVisible();
  expect(document.body).not.toHaveAttribute("data-scroll-locked");
  await user.keyboard("{Escape}");
  expect(screen.getByRole("button", { name: /Actions for/ })).toHaveFocus();
});
it("exposes empty state, native mixed selection and sortable joined column", async () => {
  const { rerender } = render(
    <NextIntlClientProvider locale="en" messages={en}>
      <CorporateMembersTable
        {...props}
        rows={members.slice(0, 2)}
        selected={[members[0]?.account_id ?? ""]}
      />
    </NextIntlClientProvider>,
  );
  expect(
    screen.getByRole("checkbox", { name: "Select all rows on this page" }),
  ).toBePartiallyChecked();
  await userEvent.setup().click(screen.getByRole("button", { name: "Joined" }));
  expect(props.update).toHaveBeenCalledWith("sort", "joined");
  rerender(
    <NextIntlClientProvider locale="en" messages={en}>
      <CorporateMembersTable {...props} rows={[]} empty />
    </NextIntlClientProvider>,
  );
  expect(screen.getByText(/No members yet/)).toBeVisible();
});
