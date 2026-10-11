import { entityMenuResult, publicActions } from "../entity-menu-fixture";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { corporateMutation } from "@/lib/api/corporate-mutation";
import type { CorporateJobTitleView, CorporateMember } from "@/lib/api/generated/types.gen";

const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutation>(),
  refresh: vi.fn(),
}));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: mutation }));
vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(",")}` : key,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import { CorporateJobTitles } from "@/components/organisms/corporate-job-titles";

const org = "organization_fixture";
const capabilities = ["job_title.list", "job_title.create", "job_title.update", "member.update"];

function title(id: string, name: string, revision = 1): CorporateJobTitleView {
  return {
    schema_version: 1,
    job_title_id: id,
    organization_id: org,
    name,
    normalized_name: name.toLowerCase(),
    description: `${name} duties`,
    state: "current",
    revision,
  };
}

function member(id: string, name: string, jobTitleId: string | null = null): CorporateMember {
  return {
    schema_version: 1,
    account_id: id,
    organization_id: org,
    scope_id: org,
    scope_kind: "organization",
    bindings: [],
    effective: [],
    grants: [],
    private_grants: [],
    authorization_revision: 7,
    available_actions: [],
    contact_email: null,
    display_name: name,
    job_title_id: jobTitleId,
    job_title_name: jobTitleId ? "Project manager" : null,
    joined_at: null,
    last_activity_at: null,
    revision: 3,
    role: "member",
    state: "active",
  };
}

const jobTitles = [title("jt_pm", "Project manager"), title("jt_sm", "Scrum master")];
const members = [
  member("acc_a", "Ada Admin"),
  member("acc_b", "Bob Builder"),
  member("acc_c", "Cid Carrier", "jt_pm"),
];

function renderPanel() {
  return render(
    <CorporateJobTitles
      csrfToken="csrf_fixture"
      organizationId={org}
      authorizationRevision={7}
      capabilities={capabilities}
      jobTitles={jobTitles}
      members={members}
    />,
  );
}

function rowMenu(name: string) {
  const button = screen.getAllByRole("button", { name })[0];
  if (!button) throw new Error(`menu not found: ${name}`);
  return button;
}

afterEach(() => {
  vi.clearAllMocks();
});

it("creates a job title through POST without an expected revision", async () => {
  mutation.mockResolvedValue({ ok: true, data: {} });
  const user = userEvent.setup();
  renderPanel();
  await user.click(screen.getByRole("button", { name: "createJobTitle" }));
  await user.type(screen.getByRole("textbox", { name: "jobTitleName" }), "Delivery lead");
  await user.click(screen.getByRole("button", { name: "save" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalled();
  });
  const call = mutation.mock.calls[0]?.[0];
  expect(call?.method).toBe("POST");
  expect(call?.path).toBe(`/v1/corporate/organizations/${org}/job-titles`);
  expect(call?.body).toMatchObject({ name: "Delivery lead", authorization_revision: 7 });
  expect(call?.body).not.toHaveProperty("expected_revision");
  expect(refresh).toHaveBeenCalled();
});

it("renames an existing title with optimistic concurrency", async () => {
  mutation.mockResolvedValue({ ok: true, data: {} });
  const user = userEvent.setup();
  renderPanel();
  await user.click(rowMenu("jobTitleActions:Project manager"));
  await user.click(await screen.findByRole("menuitem", { name: "edit" }));
  const nameInput = screen.getByRole("textbox", { name: "jobTitleName" });
  await user.clear(nameInput);
  await user.type(nameInput, "Delivery manager");
  await user.click(screen.getByRole("button", { name: "save" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalled();
  });
  const call = mutation.mock.calls[0]?.[0];
  expect(call?.method).toBe("PATCH");
  expect(call?.path).toBe(`/v1/corporate/organizations/${org}/job-titles/jt_pm`);
  expect(call?.body).toMatchObject({
    name: "Delivery manager",
    state: "current",
    expected_revision: 1,
  });
});

it("bulk-assigns a title to selected members and clears it for removed ones", async () => {
  mutation.mockResolvedValue({ ok: true, data: {} });
  const user = userEvent.setup();
  renderPanel();
  await user.click(rowMenu("jobTitleActions:Scrum master"));
  await user.click(await screen.findByRole("menuitem", { name: "assignEmployees" }));
  await user.click(await screen.findByRole("button", { name: "assignedEmployees" }));
  await user.click(await screen.findByRole("checkbox", { name: "Ada Admin" }));
  await user.click(screen.getByRole("checkbox", { name: "Bob Builder" }));
  await user.click(screen.getByRole("button", { name: "save" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalledTimes(2);
  });
  for (const call of mutation.mock.calls.map(([input]) => input)) {
    expect(call.method).toBe("PATCH");
    expect(call.body).toMatchObject({
      job_title_id: "jt_sm",
      role: "member",
      state: "active",
      expected_revision: 3,
    });
  }
  expect(mutation.mock.calls.map(([input]) => input.path).sort()).toEqual([
    `/v1/corporate/organizations/${org}/members/acc_a`,
    `/v1/corporate/organizations/${org}/members/acc_b`,
  ]);
});

it("clears an assignment from the detail panel", async () => {
  mutation.mockResolvedValue({ ok: true, data: {} });
  const user = userEvent.setup();
  renderPanel();
  // Cid Carrier holds jt_pm; open its detail drawer via the row.
  await user.click(screen.getByRole("cell", { name: "Project manager" }));
  expect(await screen.findByRole("button", { name: "personActions:Cid Carrier" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "removeAssignment" }));
  await waitFor(() => {
    expect(mutation).toHaveBeenCalled();
  });
  const call = mutation.mock.calls[0]?.[0];
  expect(call?.method).toBe("PATCH");
  expect(call?.path).toBe(`/v1/corporate/organizations/${org}/members/acc_c`);
  expect(call?.body).toMatchObject({ job_title_id: null, expected_revision: 3 });
});

vi.mock("@/lib/entity-action-query", () => ({
  queryEntityActionMenu: vi.fn((subject: EntityActionSubject) =>
    Promise.resolve(
      entityMenuResult(
        subject,
        [...publicActions.slice(0, -1), "edit", "assign_members", "retire", "report"],
        "/corporate/admin/job-titles",
      ),
    ),
  ),
}));
