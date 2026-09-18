import { expect, it } from "vitest";

import {
  corporatePresentationPath,
  corporateReferenceHref,
  entityProfileWriteRequestSchema,
  presentationFromProfile,
} from "@/lib/corporate-detail";

const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
const ids = {
  teams: "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  projects: "remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  members: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  technologies: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
} as const;

it("builds profile routes only for typed corporate identities", () => {
  const kinds = {
    teams: "team",
    projects: "project",
    members: "employee",
    technologies: "technology",
  };
  for (const [resource, id] of Object.entries(ids)) {
    expect(corporatePresentationPath(organizationId, resource as keyof typeof ids, id)).toContain(
      `/${kinds[resource as keyof typeof kinds]}/${id}`,
    );
  }
  expect(() => corporatePresentationPath(organizationId, "teams", "project_bad")).toThrow(
    "invalid corporate target",
  );
});

it("rejects unknown write fields and duplicate links before transport", () => {
  const request = {
    schema_version: 1 as const,
    fields: {
      description: "# Core",
      avatar_asset_id: null,
      links: [
        { label: "Docs", url: "https://example.com/docs" },
        { label: "Docs again", url: "https://example.com/docs" },
      ],
      media: [],
    },
    expected_revision: 0,
    authorization_revision: 1,
    idempotency_key: "corporate-profile-test-1",
  };
  expect(entityProfileWriteRequestSchema.safeParse(request).success).toBe(false);
  expect(
    entityProfileWriteRequestSchema.safeParse({
      ...request,
      fields: { ...request.fields, links: [{ label: "Docs", url: "https://example.com/docs" }] },
      extra: true,
    }).success,
  ).toBe(false);
});

it("adapts valid profile media and rejects unsafe profile receipts", () => {
  const profile = {
    name: "Core team",
    revision: 3,
    can_edit: true,
    avatar_url: "https://cdn.example.com/avatar.png",
    owner_account_id: null,
    fields: {
      description: "A short description",
      avatar_asset_id: "avatar_aaaaaaaaaaaaaaaaaaaaaaaa",
      links: [],
      media: [
        {
          kind: "image" as const,
          url: "/v1/media/component/media_123",
          alt: "Architecture diagram",
          caption: "",
        },
        {
          kind: "youtube" as const,
          url: "dQw4w9WgXcQ",
          alt: "Product demo",
          caption: "",
        },
      ],
    },
  };

  const adapted = presentationFromProfile(profile, 7);
  expect(adapted).toMatchObject({
    name: "Core team",
    authorization_revision: 7,
    media: [
      { id: "0:/v1/media/component/media_123", source_label: "Core team" },
      { id: "1:dQw4w9WgXcQ", source_label: "Core team" },
    ],
  });
  expect(
    presentationFromProfile(
      { ...profile, avatar_url: "/v1/media/avatars/avatar_aaaaaaaaaaaaaaaaaaaaaaaa" },
      7,
    ).avatar_url,
  ).toBe("/v1/media/avatars/avatar_aaaaaaaaaaaaaaaaaaaaaaaa");
  expect(() => presentationFromProfile({ ...profile, avatar_url: "/unsafe" }, 7)).toThrow();
  expect(() => presentationFromProfile(null, 7)).toThrow();
  expect(() =>
    presentationFromProfile(
      {
        ...profile,
        fields: {
          ...profile.fields,
          media: [{ ...profile.fields.media[0], url: "https://example.com/image.png" }],
        },
      },
      7,
    ),
  ).toThrow();
});

it("builds references for corporate and catalog targets with encoded IDs", () => {
  expect(corporateReferenceHref({ kind: "team", id: "team/a", name: "Core team" })).toBe(
    "/corporate/teams/team%2Fa",
  );
  expect(corporateReferenceHref({ kind: "employee", id: "account_1", name: "Alice" })).toBe(
    "/corporate/employees/account_1",
  );
  expect(corporateReferenceHref({ kind: "component", id: "component_1", name: "Skill" })).toBe(
    "/catalog/components/component_1",
  );
});
