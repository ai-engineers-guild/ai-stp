import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { updateCorporatePresentationAction } from "@/actions/corporate-detail";
import type { CorporatePresentation } from "@/lib/corporate-detail";

const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof updateCorporatePresentationAction>(),
  refresh: vi.fn(),
}));

vi.mock("@/actions/corporate-detail", () => ({
  updateCorporatePresentationAction: mutation,
}));
vi.mock("@/lib/corporate-detail-upload", () => ({
  uploadCorporateDetailMedia: vi.fn(),
}));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({ useRouter: () => ({ refresh }) }));

import { CorporateRichEditor } from "@/components/organisms/corporate-rich-editor";

const initial: CorporatePresentation = {
  name: "Core team",
  description: "Initial description",
  avatar_asset_id: null,
  avatar_url: null,
  links: [],
  media: [],
  revision: 2,
  authorization_revision: 4,
  can_edit: true,
  owner: null,
  author: null,
  owner_account_id: null,
  leads: [],
  teams: [],
  projects: [],
  technologies: [],
  components: [],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("keeps the draft and idempotency key across a failed save retry", async () => {
  mutation.mockRejectedValueOnce(new Error("connection lost"));
  mutation.mockResolvedValueOnce({ ok: false, message: "Conflict" });
  render(
    <CorporateRichEditor
      initial={initial}
      organizationId="organization_fixture"
      resource="teams"
      resourceId="team_fixture"
      csrfToken="csrf_fixture"
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "editProfile" }));
  fireEvent.change(screen.getByLabelText("description"), {
    target: { value: "Updated **description**" },
  });
  fireEvent.click(screen.getByRole("button", { name: "profileSave" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("description")).toHaveValue("Updated **description**");

  fireEvent.click(screen.getByRole("button", { name: "profileSave" }));
  await screen.findByText("Conflict");
  expect(mutation).toHaveBeenCalledTimes(2);
  expect(mutation.mock.calls[1]?.[0].data).toEqual(mutation.mock.calls[0]?.[0].data);
  expect(refresh).not.toHaveBeenCalled();
});

it("does not expose an editor when the server denies editing", () => {
  render(
    <CorporateRichEditor
      initial={{ ...initial, can_edit: false }}
      organizationId="organization_fixture"
      resource="teams"
      resourceId="team_fixture"
      csrfToken="csrf_fixture"
    />,
  );
  expect(screen.queryByRole("button", { name: "editProfile" })).not.toBeInTheDocument();
});
