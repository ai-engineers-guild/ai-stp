/* eslint-disable @typescript-eslint/require-await -- Async transport doubles preserve the production contract. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { CorporateAssignDialog } from "@/components/organisms/corporate-assign-dialog";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import { corporateAssignmentRevisionAction } from "@/actions/corporate";
const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: vi.fn() }));
vi.mock("@/actions/corporate", () => ({
  corporateCatalogVersionsAction: vi.fn(async () => ({ ok: true, versions: ["1.0"] })),
  corporateAssignmentRevisionAction: vi.fn(async () => ({ ok: true, revision: 0 })),
  corporateSubjectSearchAction: vi.fn(async ({ kind }: { kind: string }) => ({
    ok: true,
    items:
      kind === "technology"
        ? [
            { value: "technology_a", label: "Draft A" },
            { value: "technology_b", label: "Draft B" },
          ]
        : [],
  })),
}));

it("retries only failed subjects with the identical revision and idempotency key", async () => {
  const user = userEvent.setup();
  const close = vi.fn();
  vi.mocked(corporateMutation)
    .mockResolvedValueOnce({ ok: true, data: {} })
    .mockResolvedValueOnce({ ok: false, message: "API unavailable" })
    .mockResolvedValueOnce({ ok: true, data: {} });
  render(
    <CorporateAssignDialog
      open
      onOpenChange={close}
      objectKind="component"
      stableId="component_a"
      objectName="Skill"
      context={{
        ok: true,
        organizationId: "organization_a",
        authorizationRevision: 3,
        csrfToken: "csrf",
        labels: {
          assign: "Assign",
          dialogTitle: "Assign to subjects",
          version: "Version",
          latest: "Latest",
          search: "Search",
          closeFilters: "Close",
          loading: "Loading",
          assignPartial: "{saved} saved, {failed} failed.",
          assignFailed: "Failed",
          employee: "Employees",
          team: "Teams",
          project: "Projects",
          technologies: "Technologies",
        },
      }}
    />,
  );
  await user.click(await screen.findByRole("button", { name: /^Technologies/ }));
  await user.click(await screen.findByLabelText("Draft A"));
  await user.click(screen.getByLabelText("Draft B"));
  await user.click(
    within(screen.getByRole("dialog", { name: "Technologies" })).getByRole("button", {
      name: "Close",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Assign" }));
  await screen.findByText("1 saved, 1 failed. Draft B: API unavailable");
  expect(close).not.toHaveBeenCalled();
  const failed = vi.mocked(corporateMutation).mock.calls[1]?.[0];
  expect(failed?.body).toMatchObject({ subject_id: "technology_b", expected_revision: 0 });
  await user.click(screen.getByRole("button", { name: "Assign" }));
  await waitFor(() => {
    expect(close).toHaveBeenCalledWith(false);
  });
  expect(corporateMutation).toHaveBeenCalledTimes(3);
  expect(vi.mocked(corporateMutation).mock.calls[2]?.[0]).toEqual(failed);
  expect(corporateAssignmentRevisionAction).toHaveBeenCalledTimes(2);
  expect(refresh).toHaveBeenCalledTimes(2);
});
