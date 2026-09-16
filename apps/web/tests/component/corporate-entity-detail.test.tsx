import type { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CorporatePresentation } from "@/lib/corporate-detail";

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));
vi.mock("@/lib/i18n/navigation", () => ({
  Link: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));
vi.mock("@/components/organisms/object-detail-frame", () => ({
  ObjectDetailFrame: ({
    description,
    main,
    rail,
  }: {
    description: ReactNode;
    main: ReactNode;
    rail: ReactNode;
  }) => (
    <div>
      {description}
      {main}
      {rail}
    </div>
  ),
}));

import { CorporateEntityDetail } from "@/components/organisms/corporate-entity-detail";

const presentation = {
  name: "Offline technology",
  description: "Description",
  avatar_asset_id: null,
  avatar_url: null,
  links: [],
  media: [],
  revision: 0,
  authorization_revision: 1,
  can_edit: false,
  owner: { kind: "employee", id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z", name: "Ada" },
  author: { kind: "employee", id: "account_01JQZK7B8N4M6P2R9T5V0X3Y8A", name: "Grace" },
  owner_account_id: "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  leads: [],
  teams: [],
  projects: [],
  technologies: [],
  components: [],
} satisfies CorporatePresentation;

afterEach(cleanup);

describe("corporate entity owner labels", () => {
  it("links editable entities to a separate edit page", () => {
    render(
      <CorporateEntityDetail
        presentation={{ ...presentation, can_edit: true }}
        description="Description"
        resource="teams"
        resourceId="operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
      >
        <p>Main</p>
      </CorporateEntityDetail>,
    );

    expect(screen.getByRole("link", { name: "objects.editPresentation" })).toHaveAttribute(
      "href",
      "/corporate/teams/operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z/edit",
    );
    expect(screen.queryByRole("form")).toBeNull();
  });

  it("labels an employee owner as an operational owner", () => {
    render(
      <CorporateEntityDetail
        presentation={presentation}
        description="Description"
        resource="technologies"
        resourceId="technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
      >
        <p>Main</p>
      </CorporateEntityDetail>,
    );

    expect(screen.getByText("hub.operationalOwner")).toBeVisible();
    expect(screen.queryByText("hub.owner")).toBeNull();
  });

  it("keeps the team owner label for a team reference", () => {
    render(
      <CorporateEntityDetail
        presentation={{
          ...presentation,
          owner: { kind: "team", id: "operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z", name: "Core" },
        }}
        description="Description"
        resource="teams"
        resourceId="operation_01JQZK7B8N4M6P2R9T5V0X3Y7Z"
      >
        <p>Main</p>
      </CorporateEntityDetail>,
    );

    expect(screen.getByText("hub.owner")).toBeVisible();
    expect(screen.queryByText("hub.operationalOwner")).toBeNull();
  });
});
