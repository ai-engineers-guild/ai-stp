import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { updateCorporatePresentationAction } from "@/actions/corporate-detail";
import type { corporateMutationAction } from "@/actions/corporate";
import type { CorporatePresentation } from "@/lib/corporate-detail";

const { mutation, entityMutation, uploadMutation, push, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof updateCorporatePresentationAction>(),
  entityMutation: vi.fn<typeof corporateMutationAction>(),
  uploadMutation: vi.fn(),
  push: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("@/actions/corporate-detail", () => ({
  updateCorporatePresentationAction: mutation,
}));
vi.mock("@/actions/corporate", () => ({ corporateMutationAction: entityMutation }));
vi.mock("@/lib/corporate-detail-upload", () => ({
  uploadCorporateDetailMedia: uploadMutation,
}));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));
vi.mock("@/lib/i18n/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

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

it("uses the shared editable fields without an avatar block", () => {
  render(
    <CorporateRichEditor
      initial={initial}
      organizationId="organization_fixture"
      resource="teams"
      resourceId="team_fixture"
      csrfToken="csrf_fixture"
      cancelHref="/corporate/teams/team_fixture"
      entityUpdate={{ kind: "team", revision: 2, state: "active", description: "" }}
    />,
  );

  expect(screen.queryByRole("heading", { name: "avatar" })).toBeNull();
  expect(screen.getByLabelText("profileDisplayName")).toBeEnabled();
  expect(screen.getByRole("heading", { name: "media" })).toBeVisible();
  expect(screen.getByText("mediaHelp")).toBeVisible();
  expect(screen.getByText("mediaRequirements")).toBeVisible();
  expect(screen.getByRole("button", { name: "addMedia" })).toBeVisible();
  expect(screen.queryByRole("button", { name: "editProfile" })).toBeNull();
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
      cancelHref="/corporate/teams/team_fixture"
      entityUpdate={{ kind: "team", revision: 2, state: "active", description: "" }}
    />,
  );

  fireEvent.change(screen.getByLabelText("description"), {
    target: { value: "Updated **description**" },
  });
  fireEvent.click(screen.getByRole("button", { name: "profileSave" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("description")).toHaveValue("Updated **description**");

  await screen.findByRole("button", { name: "profileSave" });
  fireEvent.click(screen.getByRole("button", { name: "profileSave" }));
  await screen.findByText("Conflict");
  expect(mutation).toHaveBeenCalledTimes(2);
  expect(mutation.mock.calls[1]?.[0].data).toEqual(mutation.mock.calls[0]?.[0].data);
  expect(push).not.toHaveBeenCalled();
});

it("uploads media through the same media item widget", async () => {
  uploadMutation.mockResolvedValue({
    avatar_asset_id: "avatar_0123456789abcdef01234567",
    media_id: "avatar_0123456789abcdef01234567",
    public_url: "/v1/media/avatars/avatar_0123456789abcdef01234567",
    kind: "image",
  });
  const { container } = render(
    <CorporateRichEditor
      initial={initial}
      organizationId="organization_fixture"
      resource="teams"
      resourceId="team_fixture"
      csrfToken="csrf_fixture"
      cancelHref="/corporate/teams/team_fixture"
      entityUpdate={{ kind: "team", revision: 2, state: "active", description: "" }}
    />,
  );

  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  const file = new File([new Uint8Array([0xff, 0xd8, 0xff])], "cover.jpg", {
    type: "image/jpeg",
  });
  if (!input) throw new Error("media file input missing");
  fireEvent.change(input, { target: { files: [file] } });

  await waitFor(() => {
    expect(uploadMutation).toHaveBeenCalled();
  });
  expect(uploadMutation).toHaveBeenCalledWith(expect.objectContaining({ purpose: "media" }), file);
});

it("persists an edited display name through the entity endpoint", async () => {
  entityMutation.mockResolvedValue({ ok: true, data: {} });
  mutation.mockResolvedValue({
    ok: true,
    data: {
      name: "Renamed team",
      revision: 3,
      can_edit: true,
      avatar_url: null,
      owner_account_id: null,
      fields: { description: "Initial description", avatar_asset_id: null, links: [], media: [] },
    },
  });
  render(
    <CorporateRichEditor
      initial={initial}
      organizationId="organization_fixture"
      resource="teams"
      resourceId="team_fixture"
      csrfToken="csrf_fixture"
      cancelHref="/corporate/teams/team_fixture"
      entityUpdate={{ kind: "team", revision: 2, state: "active", description: "" }}
    />,
  );

  fireEvent.change(screen.getByLabelText("profileDisplayName"), {
    target: { value: "Renamed team" },
  });
  fireEvent.click(screen.getByRole("button", { name: "profileSave" }));

  await waitFor(() => {
    expect(push).toHaveBeenCalledWith("/corporate/teams/team_fixture");
  });
  const [request] = entityMutation.mock.calls[0] ?? [];
  expect(request).toBeDefined();
  expect(request?.body).toMatchObject({ name: "Renamed team" });
});

it("does not expose an editor when the server denies editing", () => {
  render(
    <CorporateRichEditor
      initial={{ ...initial, can_edit: false }}
      organizationId="organization_fixture"
      resource="teams"
      resourceId="team_fixture"
      csrfToken="csrf_fixture"
      cancelHref="/corporate/teams/team_fixture"
      entityUpdate={{ kind: "team", revision: 2, state: "active", description: "" }}
    />,
  );
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
});
