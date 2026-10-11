import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { expect, it, vi } from "vitest";
import messages from "../../messages/en.json";
import { member, context } from "@/stories/UI Kit/Organisms/CorporateMemberRouteDialog.stories";
import {
  CorporateMemberRouteDialog,
  CorporateGrantRouteDialog,
} from "@/components/organisms/corporate-member-route-dialog";
const { back } = vi.hoisted(() => ({ back: vi.fn() }));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ back, refresh: vi.fn() }) }));
it("edits a member on the current page and returns through history", async () => {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CorporateMemberRouteDialog
        member={member}
        context={context}
        roles={[]}
        jobTitles={[]}
        csrfToken=""
      />
    </NextIntlClientProvider>,
  );
  expect(screen.getByRole("dialog", { name: messages.people.editMember })).toBeVisible();
  expect(screen.getByDisplayValue(member.display_name ?? "")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: messages.corporate.cancel }));
  expect(back).toHaveBeenCalledTimes(1);
});
it("opens access immediately with the subject selected", () => {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CorporateGrantRouteDialog
        csrfToken=""
        organizationId={context.organization.organization_id}
        authorizationRevision={0}
        members={[member]}
        initialMemberIds={[member.account_id]}
        roles={[]}
        grantableRoleNames={[]}
        teams={[]}
        projects={[]}
        scopeOptions={[]}
        definitions={[]}
        capabilities={[]}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.getByRole("dialog", { name: messages.accessUi.grantAccess })).toBeVisible();
  expect(document.querySelector('input[name="members"][value="account_example"]')).toBeChecked();
});
