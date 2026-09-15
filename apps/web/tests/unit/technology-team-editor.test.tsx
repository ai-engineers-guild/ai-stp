import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { corporateMutationAction } from "@/actions/corporate";
const { mutation } = vi.hoisted(() => ({ mutation: vi.fn<typeof corporateMutationAction>() }));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
import { TechnologyTeamEditor } from "@/components/organisms/technology-governance-editors";
const teamId = "operation_00000000000000000000000001";
const relation = {
  organization_id: "organization_fixture",
  technology_id: "technology_fixture",
  team_id: teamId,
  relation_id: "operation_relation",
  revision: 4,
  state: "retired" as const,
};
const props = {
  organizationId: "organization_fixture",
  technologyId: "technology_fixture",
  authorizationRevision: "revision_fixture",
  csrfToken: "csrf_fixture",
  teams: [{ value: teamId, label: "Mobile" }],
};
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("selects a retired relation by team name and restores it with its hidden revision", async () => {
  mutation.mockResolvedValue({ ok: false, message: "Conflict" });
  const { container } = render(
    <TechnologyTeamEditor
      {...props}
      relations={[relation]}
      capabilities={["technology_team.create", "technology_team.update"]}
    />,
  );
  const details = container.querySelector("details");
  if (!details) throw new Error("selector missing");
  details.open = true;
  fireEvent.click(screen.getByRole("checkbox", { name: "Mobile" }));
  fireEvent.click(screen.getByRole("button", { name: "saveChanges" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalledOnce();
  });
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    team_id: teamId,
    state: "current",
    expected_revision: 4,
  });
  await screen.findByText("Conflict");
});

it("does not enable save when only unlinking is authorized", () => {
  render(
    <TechnologyTeamEditor
      {...props}
      initial={{ ...relation, state: "current" }}
      capabilities={["technology_team.delete"]}
    />,
  );
  expect(screen.getByRole("button", { name: "saveChanges" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "unlink" })).toBeEnabled();
});

it("recovers from a transport rejection and retries the unchanged effect with the same key", async () => {
  mutation.mockRejectedValueOnce(new Error("connection lost"));
  mutation.mockResolvedValueOnce({ ok: false, message: "Conflict" });
  render(
    <TechnologyTeamEditor
      {...props}
      initial={{ ...relation, state: "current" }}
      capabilities={["technology_team.delete"]}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "unlink" }));
  await screen.findByText("unavailable");
  expect(screen.getByRole("button", { name: "unlink" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "unlink" }));
  await screen.findByText("Conflict");
  expect(mutation.mock.calls[1]?.[0].body).toEqual(mutation.mock.calls[0]?.[0].body);
});
