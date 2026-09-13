import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { corporateMutationAction } from "@/actions/corporate";
const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
}));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh }),
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
import { ProjectTeamEditor } from "@/components/organisms/project-team-editor";
afterEach(cleanup);

it("links by name and includes both revisions for an atomic owner replacement", async () => {
  mutation.mockResolvedValue({ ok: false, message: "Conflict" });
  const { container } = render(
    <ProjectTeamEditor
      organizationId="organization_fixture"
      projectId="project_fixture"
      authorizationRevision="revision_fixture"
      csrfToken="csrf_fixture"
      capabilities={["project_team.create"]}
      teams={[
        { team_id: "team_old", name: "Old" },
        { team_id: "team_mobile", name: "Mobile" },
      ]}
      relations={[
        {
          organization_id: "organization_fixture",
          project_id: "project_fixture",
          team_id: "team_old",
          relation_id: "relation_old",
          revision: 3,
          role: "owner",
          state: "current",
        },
      ]}
    />,
  );
  expect(screen.getByRole("link", { name: "Old" })).toHaveAttribute(
    "href",
    "/corporate/teams/team_old",
  );
  container.querySelectorAll("details").forEach((item) => {
    item.open = true;
  });
  fireEvent.click(screen.getByRole("checkbox", { name: "Mobile" }));
  fireEvent.change(screen.getByLabelText("teamRole"), { target: { value: "owner" } });
  expect(screen.getByText("replaceOwner")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalledOnce();
  });
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    team_id: "team_mobile",
    expected_revision: 0,
    role: "owner",
    state: "current",
    replace_owner_relation_id: "relation_old",
    replace_owner_expected_revision: 3,
  });
  await screen.findByText("Conflict");
  expect(refresh).not.toHaveBeenCalled();
});
