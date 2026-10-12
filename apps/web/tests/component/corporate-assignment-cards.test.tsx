import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import { render } from "../render-with-intl";
import { entityMenuResult } from "../entity-menu-fixture";
import messages from "../../messages/en.json";
import { CorporateCatalogAssignments } from "@/components/organisms/corporate-catalog-assignments";
import { componentSummaryFixture } from "@/mocks/fixtures/catalog";
import { assignmentCardItem } from "@/lib/assignment-card";
import { queryEntityActionMenu } from "@/lib/entity-action-query";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import type { CorporateCatalogAssignment } from "@/lib/api/generated/types.gen";

vi.mock("@/lib/entity-action-query", () => ({ queryEntityActionMenu: vi.fn() }));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: vi.fn() }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  Link: ({ children, href, ...props }: ComponentProps<"a">) => (
    <a {...props} href={href}>
      {children}
    </a>
  ),
}));
afterEach(() => {
  vi.clearAllMocks();
});

const assignment: CorporateCatalogAssignment = {
  schema_version: 1,
  assignment_id: "operation_00000000000000000000000001",
  organization_id: "organization_00000000000000000000000001",
  subject_kind: "team",
  subject_id: "operation_00000000000000000000000002",
  object_kind: "component",
  stable_id: componentSummaryFixture.stable_id,
  display_name: componentSummaryFixture.latest_name,
  selector: "latest",
  version: null,
  passport_digest: null,
  harness: "codex",
  state: "current",
  revision: 3,
  source_team_id: null,
};
function Cards({ inherited = false }: { inherited?: boolean }) {
  const row = { ...assignment, source_team_id: inherited ? assignment.subject_id : null };
  return (
    <CorporateCatalogAssignments
      items={[row]}
      cards={{ [row.assignment_id]: assignmentCardItem(row, componentSummaryFixture) }}
      authors={{
        [componentSummaryFixture.publisher_id]: {
          displayName: "Artem Letyushev",
          avatarUrl: "/avatar.png",
        },
      }}
      organizationId={row.organization_id}
      subjectKind="team"
      subjectId={row.subject_id}
      authorizationRevision={4}
      csrfToken="csrf"
      canManage
    />
  );
}

it("shows the publisher name and avatar, puts assign before filters and unlinks from the menu", async () => {
  vi.mocked(queryEntityActionMenu).mockImplementation((subject) =>
    Promise.resolve(
      entityMenuResult(subject, ["open", "unlink"], `/catalog/components/${subject.id}`),
    ),
  );
  vi.mocked(corporateMutation).mockResolvedValue({ ok: true, data: {} });
  const user = userEvent.setup();
  render(<Cards />);
  const publisher = screen.getByRole("link", { name: "Artem Letyushev" });
  expect(publisher).toHaveAttribute("href", `/publishers/${componentSummaryFixture.publisher_id}`);
  const avatar = publisher.querySelector("img");
  expect(avatar).not.toBeNull();
  expect(new URL(avatar?.getAttribute("src") ?? "").searchParams.get("url")).toBe("/avatar.png");
  expect(screen.queryByText(componentSummaryFixture.publisher_id)).toBeNull();
  const assign = screen.getByRole("button", { name: messages.hub.assignCatalog });
  const filters = screen.getByRole("button", { name: messages.hub.filters });
  expect(assign.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(assign).toHaveClass("bg-primary");
  expect(screen.queryByRole("button", { name: messages.hub.unlink })).toBeNull();
  await user.click(screen.getByRole("button", { name: messages.catalog.moreActions }));
  await user.click(await screen.findByRole("menuitem", { name: messages.hub.unlink }));
  await waitFor(() => {
    expect(corporateMutation).toHaveBeenCalledTimes(1);
  });
  expect(vi.mocked(queryEntityActionMenu).mock.calls[0]?.[0].assignment_id).toBe(
    assignment.assignment_id,
  );
  expect(vi.mocked(corporateMutation).mock.calls[0]?.[0].body).toMatchObject({
    subject_kind: "team",
    subject_id: assignment.subject_id,
    stable_id: assignment.stable_id,
    selector: "latest",
    version: null,
    harness: "codex",
    state: "retired",
    expected_revision: 3,
  });
});

it("keeps inherited assignments attached to their source team", async () => {
  vi.mocked(queryEntityActionMenu).mockImplementation((subject) =>
    Promise.resolve(entityMenuResult(subject, ["open"], `/catalog/components/${subject.id}`)),
  );
  const user = userEvent.setup();
  render(<Cards inherited />);
  expect(screen.getByRole("link", { name: messages.hub.viaTeam })).toBeVisible();
  await user.click(screen.getByRole("button", { name: messages.catalog.moreActions }));
  await screen.findByRole("menuitem", { name: messages.hub.openDetails });
  expect(vi.mocked(queryEntityActionMenu).mock.calls[0]?.[0].assignment_id).toBeUndefined();
  expect(screen.queryByRole("menuitem", { name: messages.hub.unlink })).toBeNull();
  expect(corporateMutation).not.toHaveBeenCalled();
});
