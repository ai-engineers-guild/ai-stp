import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { NextIntlClientProvider } from "next-intl";
import messages from "../../messages/en.json";
import { CorporateProjectRepository } from "@/components/organisms/corporate-project-repository";
import type { CorporateProjectView } from "@/lib/api/generated/types.gen";
const { mutation } = vi.hoisted(() => ({ mutation: vi.fn() }));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(() => {
  cleanup();
  mutation.mockReset();
});
const project: CorporateProjectView = {
  schema_version: 1,
  project_id: "remote_project_test",
  organization_id: "organization_test",
  name: "Project",
  state: "active",
  revision: 1,
  repositories: [],
  available_actions: [],
};
function view(value = project, canManage = true) {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CorporateProjectRepository
        project={value}
        organizationId="organization_test"
        authorizationRevision={1}
        csrfToken="csrf"
        canManage={canManage}
      />
    </NextIntlClientProvider>,
  );
}
it("requires an explicit check and confirmation; never launches a scan", async () => {
  const user = userEvent.setup();
  view();
  expect(mutation).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Link GitHub / GitLab" }));
  await user.type(screen.getByLabelText("Repository URL"), "https://github.com/owner/repo");
  mutation.mockResolvedValueOnce({
    ok: true,
    data: {
      plan_key: "plan",
      plan_digest: "digest",
      name: "owner/repo",
      repository_url: "https://github.com/owner/repo",
      provider: "github",
      default_branch: "main",
      observed_at: null,
      observed_revision: null,
    },
  });
  await user.click(screen.getByRole("button", { name: "Check repository" }));
  expect(await screen.findByRole("button", { name: "Link repository" })).toBeVisible();
  expect(mutation).toHaveBeenCalledTimes(1);
  expect((mutation.mock.calls[0]?.[0] as { path: string }).path).toMatch(/repository-plan$/);
  mutation.mockResolvedValueOnce({ ok: true, data: project });
  await user.click(screen.getByRole("button", { name: "Link repository" }));
  expect(mutation).toHaveBeenCalledTimes(2);
  expect((mutation.mock.calls[1]?.[0] as { path: string }).path).toMatch(/repository$/);
});
it("shows the linked provider, URL and branch without a write control", () => {
  view({
    ...project,
    repositories: [
      {
        provider_project_id: "provider",
        provider: "github",
        namespace: "owner/repo",
        repository_url: "https://github.com/owner/repo",
        default_branch: "main",
        observed_at: null,
        observed_revision: null,
      },
    ],
  });
  expect(screen.getByRole("link", { name: "owner/repo" })).toHaveAttribute(
    "href",
    "https://github.com/owner/repo",
  );
  expect(screen.getByText("main")).toBeVisible();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
it("hides linking from a read-only project viewer", () => {
  view(project, false);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
