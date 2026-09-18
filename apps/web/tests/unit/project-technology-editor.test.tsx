import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { corporateMutationAction } from "@/actions/corporate";
import type { ProjectTechnologyView } from "@/lib/api/generated/types.gen";
const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
}));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
import { ProjectTechnologyEditor } from "@/components/organisms/project-technology-editor";
const props = {
  organizationId: "organization_fixture",
  projectId: "project_fixture",
  authorizationRevision: "revision_fixture",
  csrfToken: "csrf_fixture",
  technologies: [{ technology_id: "technology_fixture", name: "Flutter" }],
};
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

it("selects by name, hides service fields and retains a failed draft and retry key", async () => {
  mutation.mockResolvedValue({ ok: false, message: "Conflict" });
  const { container } = render(
    <ProjectTechnologyEditor {...props} capabilities={["project_technology.create"]} />,
  );
  expect(screen.queryByLabelText("relationRevision")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("review")).not.toBeInTheDocument();
  const details = container.querySelector("details");
  if (!details) throw new Error("selector missing");
  details.open = true;
  fireEvent.click(screen.getByRole("checkbox", { name: "Flutter" }));
  fireEvent.change(screen.getByLabelText("version"), { target: { value: "3.x" } });
  fireEvent.click(screen.getByRole("button", { name: "saveUsage" }));
  await screen.findByText("Conflict");
  expect(screen.getByLabelText("version")).toHaveValue("3.x");
  await waitFor(() => expect(screen.getByRole("button", { name: "saveUsage" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "saveUsage" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalledTimes(2);
  });
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    technology_id: "technology_fixture",
    expected_revision: 0,
    review: "confirmed",
    fact: { version_kind: "declared_range", version: "3.x" },
  });
  expect(mutation.mock.calls[1]?.[0].body).toEqual(mutation.mock.calls[0]?.[0].body);
  expect(refresh).not.toHaveBeenCalled();
});

it("saves the selected usage context without requesting evidence", async () => {
  mutation.mockResolvedValue({ ok: false, message: "Conflict" });
  const { container } = render(
    <ProjectTechnologyEditor {...props} capabilities={["project_technology.create"]} />,
  );
  const details = container.querySelector("details");
  if (!details) throw new Error("selector missing");
  details.open = true;
  fireEvent.click(screen.getByRole("checkbox", { name: "Flutter" }));
  fireEvent.change(screen.getByLabelText("context"), { target: { value: "testing" } });
  fireEvent.click(screen.getByRole("button", { name: "saveUsage" }));
  await screen.findByText("Conflict");
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    fact: { context: "testing", version_kind: "unknown", evidence: [] },
  });
});

it("unlinks the whole relation using delete permission and the hidden loaded revision", async () => {
  mutation.mockResolvedValue({ ok: true, data: {} });
  const { container } = render(
    <ProjectTechnologyEditor
      {...props}
      capabilities={["project_technology.delete"]}
      usages={[
        {
          organization_id: props.organizationId,
          project_id: props.projectId,
          technology_id: "technology_fixture",
          relation_id: "relation_fixture",
          revision: 4,
          state: "current",
          facts: [],
        },
      ]}
    />,
  );
  const details = container.querySelector("details");
  if (!details) throw new Error("selector missing");
  details.open = true;
  fireEvent.click(screen.getByRole("checkbox", { name: "Flutter" }));
  expect(screen.getByRole("button", { name: "saveUsage" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "unlink" }));
  await waitFor(() => {
    expect(refresh).toHaveBeenCalledOnce();
  });
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    technology_id: "technology_fixture",
    state: "retired",
    expected_revision: 4,
  });
});

it("retains an unchanged observed version and uses the loaded revision", async () => {
  mutation.mockResolvedValue({ ok: false, message: "Conflict" });
  const usage: ProjectTechnologyView = {
    organization_id: props.organizationId,
    project_id: props.projectId,
    technology_id: "technology_fixture",
    relation_id: "relation_fixture",
    revision: 4,
    state: "current",
    facts: [
      {
        context: "production",
        review: "proposed",
        freshness: "current",
        version_kind: "observed_version",
        version: "3.1",
        evidence: [],
      },
    ],
  };
  const { container } = render(
    <ProjectTechnologyEditor
      {...props}
      capabilities={["project_technology.update"]}
      usages={[usage]}
    />,
  );
  const details = container.querySelector("details");
  if (!details) throw new Error("selector missing");
  details.open = true;
  fireEvent.click(screen.getByRole("checkbox", { name: "Flutter" }));
  expect(screen.getByLabelText("version")).toHaveValue("3.1");
  fireEvent.click(screen.getByRole("button", { name: "saveUsage" }));
  await screen.findByText("Conflict");
  expect(mutation.mock.calls[0]?.[0].body).toMatchObject({
    expected_revision: 4,
    fact: { version_kind: "observed_version", version: "3.1", evidence: [] },
  });
});
