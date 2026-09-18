import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { corporateMutationAction } from "@/actions/corporate";
const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
}));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh }),
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
import { CorporateProjectMemberships } from "@/components/organisms/corporate-project-memberships";
afterEach(cleanup);

it("links an employee to a named project and retains selection on failure", async () => {
  mutation.mockResolvedValue({ ok: false, message: "Conflict" });
  const { container } = render(
    <CorporateProjectMemberships
      organizationId="organization_fixture"
      authorizationRevision={3}
      csrfToken="csrf_fixture"
      accountId="account_alex"
      options={[{ id: "project_mobile", name: "Mobile application" }]}
      assigned={[]}
      canManage
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "addMembership" }));
  const details = container.querySelector("details");
  if (!details) throw new Error("selector missing");
  details.open = true;
  fireEvent.click(screen.getByRole("checkbox", { name: "Mobile application" }));
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("checkbox", { name: "Mobile application" })).toBeChecked();
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    account_id: "account_alex",
    project_id: "project_mobile",
    operation: "assign",
  });
  expect(refresh).not.toHaveBeenCalled();
});
