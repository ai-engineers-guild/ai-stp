import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { corporateMutation } from "@/lib/api/corporate-mutation";
import type { CorporateCatalogOwnerMember } from "@/lib/api/corporate-catalog-ownership";

const { mutation, refresh } = vi.hoisted(() => ({
  mutation: vi.fn<typeof corporateMutation>(),
  refresh: vi.fn(),
}));

vi.mock("@/lib/api/corporate-mutation", () => ({ corporateMutation: mutation }));
vi.mock("@/lib/i18n/navigation", () => ({ useRouter: () => ({ refresh }) }));
vi.mock("next-intl", () => ({ useTranslations: () => (key: string) => key }));

import { CorporateCatalogOwnerDialog } from "@/components/organisms/corporate-catalog-owner-editor";

const stableId = "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const ownerId = "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const nextOwnerId = "account_01JQZK7B8N4M6P2R9T5V0X3Y8B";
const members = [
  { id: ownerId, name: "Current owner" },
  { id: nextOwnerId, name: "New owner" },
] satisfies CorporateCatalogOwnerMember[];

const props = {
  ownership: {
    can_edit: true,
    capabilities: [],
    object_kind: "component" as const,
    organization_id: organizationId,
    owner_id: ownerId,
    owner_kind: "employee" as const,
    owner_account_id: ownerId,
    owner_display_name: "Current owner",
    revision: 7,
    schema_version: 1 as const,
    stable_id: stableId,
  },
  objectKind: "component" as const,
  stableId,
  version: "1.2.3",
  organizationId,
  authorizationRevision: 9,
  csrfToken: "csrf_fixture",
  members,
};

beforeEach(() => {
  vi.resetAllMocks();
  mutation.mockResolvedValue({
    ok: true,
    data: props.ownership,
  });
});
afterEach(cleanup);

describe("corporate catalog owner editor", () => {
  it("searches employees and chooses exactly one operational owner", async () => {
    render(<CorporateCatalogOwnerDialog open onOpenChange={() => {}} ownerEdit={props} />);
    fireEvent.click(screen.getByLabelText("operationalOwner: Current owner"));
    fireEvent.change(screen.getByRole("searchbox", { name: "search" }), {
      target: { value: "New" },
    });
    expect(screen.queryByRole("checkbox", { name: "Current owner" })).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: "New owner" }));
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledOnce();
    });
    expect(mutation.mock.calls[0]?.[0].body).toMatchObject({ owner_account_id: nextOwnerId });
  });
  it("supports nullable unassign with revision and retry-safe mutation data", async () => {
    mutation
      .mockResolvedValueOnce({ ok: false, message: "Conflict" })
      .mockResolvedValueOnce({ ok: true, data: props.ownership });
    render(<CorporateCatalogOwnerDialog open onOpenChange={() => {}} ownerEdit={props} />);

    fireEvent.click(screen.getByLabelText("operationalOwner: Current owner"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Current owner" }));
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    await screen.findByText("Conflict");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "save" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    await waitFor(() => {
      expect(mutation).toHaveBeenCalledTimes(2);
    });

    const first = mutation.mock.calls[0]?.[0];
    const second = mutation.mock.calls[1]?.[0];
    if (!first || !second || typeof first.body !== "object" || !first.body) {
      throw new Error("mutation calls are missing");
    }
    if (typeof second.body !== "object" || !second.body) {
      throw new Error("retry mutation body is missing");
    }
    expect(first).toMatchObject({
      method: "PUT",
      path: `/v1/corporate/organizations/${organizationId}/catalog-ownership`,
      body: {
        object_kind: "component",
        stable_id: stableId,
        version: "1.2.3",
        owner_account_id: null,
        expected_revision: 7,
        authorization_revision: 9,
      },
    });
    expect((first.body as { idempotency_key: string }).idempotency_key).toBe(
      (second.body as { idempotency_key: string }).idempotency_key,
    );
  });

  it("rejects a mismatched successful response", async () => {
    mutation.mockResolvedValueOnce({
      ok: true,
      data: { ...props.ownership, stable_id: "component_01JQZK7B8N4M6P2R9T5V0X3Y8A" },
    });
    render(<CorporateCatalogOwnerDialog open onOpenChange={() => {}} ownerEdit={props} />);

    fireEvent.click(screen.getByLabelText("operationalOwner: Current owner"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Current owner" }));
    fireEvent.click(screen.getByRole("button", { name: "save" }));

    await screen.findByText("failed");
    expect(refresh).not.toHaveBeenCalled();
  });
});
