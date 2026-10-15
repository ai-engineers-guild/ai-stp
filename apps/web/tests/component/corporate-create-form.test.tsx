import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, expect, it, vi } from "vitest";
import messages from "../../messages/en.json";
import { CorporateCreateForm } from "@/components/organisms/corporate-create-form";
import { corporateMutation } from "@/lib/api/corporate-mutation";
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, back: vi.fn() }) }));
afterEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
});
it("creates an employee with organization relations and no catalog assignment", async () => {
  vi.mocked(corporateMutation).mockResolvedValue({ ok: true, data: {} });
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CorporateCreateForm
        resource="members"
        organizationId="organization_fixture"
        authorizationRevision={2}
        csrfToken="csrf"
        roles={["staff"]}
        teams={[]}
        employees={[]}
        projects={[]}
        technologies={[]}
        jobTitles={[]}
      />
    </NextIntlClientProvider>,
  );
  expect(screen.queryByText(messages.hub.component, { exact: true })).toBeNull();
  fireEvent.change(screen.getByLabelText(messages.corporate.displayName), {
    target: { value: "New employee" },
  });
  fireEvent.change(screen.getByLabelText(messages.corporate.email), {
    target: { value: "new@example.test" },
  });
  fireEvent.click(screen.getByRole("button", { name: messages.corporate.create }));
  await waitFor(() => {
    expect(replace).toHaveBeenCalled();
  });
  expect(vi.mocked(corporateMutation).mock.calls[0]?.[0].body).toMatchObject({
    display_name: "New employee",
    email: "new@example.test",
    role: "staff",
    team_ids: [],
    project_ids: [],
    job_title_id: null,
  });
  expect(vi.mocked(corporateMutation).mock.calls[0]?.[0].body).not.toHaveProperty(
    "catalog_assignments",
  );
});
