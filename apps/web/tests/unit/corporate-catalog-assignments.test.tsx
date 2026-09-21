import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type {
  corporateCatalogSearchAction,
  corporateCatalogVersionsAction,
  corporateMutationAction,
} from "@/actions/corporate";
const { search, versions, mutation, refresh } = vi.hoisted(() => ({
  search: vi.fn<typeof corporateCatalogSearchAction>(),
  versions: vi.fn<typeof corporateCatalogVersionsAction>(),
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
}));
vi.mock("@/actions/corporate", () => ({
  corporateCatalogSearchAction: search,
  corporateCatalogVersionsAction: versions,
  corporateMutationAction: mutation,
}));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({
  useRouter: () => ({ refresh }),
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));
import { CorporateCatalogAssignments } from "@/components/organisms/corporate-catalog-assignments";
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("assigns Mobile Development by name and exact version without installing", async () => {
  search.mockResolvedValue({
    ok: true,
    items: [{ id: "setup_mobile", name: "Mobile Development" }],
  });
  versions.mockResolvedValue({ ok: true, versions: ["2.0", "1.0"] });
  mutation.mockResolvedValue({ ok: false, message: "Conflict" });
  render(
    <CorporateCatalogAssignments
      items={[]}
      organizationId="organization_fixture"
      subjectKind="team"
      subjectId="team_mobile"
      authorizationRevision={3}
      csrfToken="csrf_fixture"
      canManage
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "assignCatalog" }));
  fireEvent.change(screen.getByLabelText("search"), { target: { value: "Mobile" } });
  fireEvent.click(screen.getByRole("button", { name: "search" }));
  fireEvent.click(await screen.findByRole("button", { name: "Mobile Development" }));
  await waitFor(() => expect(screen.getByLabelText("exactVersion")).toHaveValue("2.0"));
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await screen.findByRole("alert");
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    subject_kind: "team",
    subject_id: "team_mobile",
    object_kind: "setup",
    stable_id: "setup_mobile",
    version: "2.0",
    state: "current",
    expected_revision: 0,
  });
  expect(mutation.mock.calls[0]?.[0].body).not.toHaveProperty("install");
  expect(refresh).not.toHaveBeenCalled();
});

it("hides retired assignments but uses their revision to assign the same version again", async () => {
  search.mockResolvedValue({
    ok: true,
    items: [{ id: "setup_mobile", name: "Mobile Development" }],
  });
  versions.mockResolvedValue({ ok: true, versions: ["2.0"] });
  mutation.mockResolvedValue({ ok: true, data: {} });
  render(
    <CorporateCatalogAssignments
      items={[
        {
          schema_version: 1,
          assignment_id: "operation_assignment",
          organization_id: "organization_fixture",
          subject_kind: "team",
          subject_id: "operation_mobile",
          object_kind: "setup",
          stable_id: "setup_mobile",
          version: "2.0",
          selector: "exact" as const,
          passport_digest: null,
          harness: null,
          state: "retired",
          revision: 2,
          source_team_id: null,
          display_name: "Old assignment",
        },
      ]}
      organizationId="organization_fixture"
      subjectKind="team"
      subjectId="operation_mobile"
      authorizationRevision={3}
      csrfToken="csrf_fixture"
      canManage
    />,
  );
  expect(screen.queryByText(/Old assignment/)).not.toBeInTheDocument();
  expect(screen.getByText("noAssignments")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "assignCatalog" }));
  fireEvent.click(screen.getByRole("button", { name: "search" }));
  fireEvent.click(await screen.findByRole("button", { name: "Mobile Development" }));
  await waitFor(() => expect(screen.getByLabelText("exactVersion")).toHaveValue("2.0"));
  fireEvent.click(screen.getByRole("button", { name: "save" }));
  await waitFor(() => {
    expect(refresh).toHaveBeenCalledOnce();
  });
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    expected_revision: 2,
    state: "current",
  });
});
