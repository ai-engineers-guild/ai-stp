import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { corporateMutationAction } from "@/actions/corporate";

const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutationAction>(),
  refresh: vi.fn(),
}));

vi.mock("@/actions/corporate", () => ({ corporateMutationAction: mutation }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import { CorporateAdminPanel } from "@/components/organisms/corporate-admin-panel";

const labels = {
  title: "Administration",
  description: "Manage",
  members: "Members",
  projects: "Projects",
  teams: "Teams",
  roles: "Roles",
  displayName: "Display name",
  email: "Email",
  name: "Name",
  role: "Role",
  parentRole: "Parent role",
  permissions: "Permissions",
  staff: "Staff",
  lead: "Lead",
  create: "Create",
  creating: "Creating",
  saved: "Saved",
  failed: "Failed",
  jobTitles: "Job titles",
  jobTitleName: "Job title",
  jobTitleDescription: "Description",
  jobTitleState: "State",
  jobTitleCurrent: "Current",
  jobTitleRetired: "Retired",
  jobTitleSave: "Save job title",
  jobTitleNoItems: "No job titles",
};

describe("CorporateAdminPanel job titles", () => {
  it("keeps the dedicated page scoped to job-title controls", () => {
    render(
      <CorporateAdminPanel
        jobTitlesOnly
        csrfToken="csrf"
        organizationId="organization_fixture"
        authorizationRevision={7}
        permissions={["member.create", "project.create", "team.create", "job_title.create"]}
        labels={labels}
      />,
    );
    expect(screen.getByLabelText("Job title")).toBeInTheDocument();
    expect(screen.queryByLabelText("Display name")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Projects" })).not.toBeInTheDocument();
  });

  it("creates and revision-updates a job title through capabilities", async () => {
    mutation.mockResolvedValue({ ok: true, data: {} });
    render(
      <CorporateAdminPanel
        csrfToken="csrf"
        organizationId="organization_fixture"
        authorizationRevision={7}
        permissions={["job_title.create", "job_title.update"]}
        jobTitles={[
          {
            schema_version: 1,
            job_title_id: "job_title_fixture",
            organization_id: "organization_fixture",
            name: "Engineer",
            normalized_name: "engineer",
            description: "Builds things",
            state: "current",
            revision: 3,
          },
        ]}
        labels={labels}
      />,
    );

    const createFields = screen.getAllByLabelText("Job title");
    if (!createFields[0]) throw new Error("create job title field is missing");
    fireEvent.change(createFields[0], {
      target: { value: "Architect" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => {
      expect(mutation).toHaveBeenCalled();
    });
    const createCall = mutation.mock.calls[0]?.[0];
    if (!createCall) throw new Error("create mutation was not captured");
    expect(createCall).toMatchObject({
      method: "POST",
      path: "/v1/corporate/organizations/organization_fixture/job-titles",
    });
    expect(createCall.body).toMatchObject({ name: "Architect", authorization_revision: 7 });

    const inputs = screen.getAllByLabelText("Job title");
    if (!inputs[1]) throw new Error("edit job title field is missing");
    fireEvent.change(inputs[1], { target: { value: "Principal architect" } });
    fireEvent.click(screen.getByRole("button", { name: "Save job title" }));
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledTimes(2);
    });
    const updateCall = mutation.mock.calls[1]?.[0];
    if (!updateCall) throw new Error("update mutation was not captured");
    expect(updateCall).toMatchObject({
      method: "PATCH",
      path: "/v1/corporate/organizations/organization_fixture/job-titles/job_title_fixture",
    });
    expect(updateCall.body).toMatchObject({
      name: "Principal architect",
      expected_revision: 3,
      authorization_revision: 7,
    });
  });
});
