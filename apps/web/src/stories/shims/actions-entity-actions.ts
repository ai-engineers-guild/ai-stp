import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
export async function loadEntityActionMenus(subjects: EntityActionSubject[]) {
  return {
    csrfToken: "storybook",
    menus: {
      schema_version: 1 as const,
      items: subjects.map((subject) => ({
        subject,
        revision: null,
        authorization_revision: null,
        object_version: null,
        object_name: null,
        visibility: null,
        device_id: null,
        href: "/corporate/teams/team_example",
        actions: [
          { id: "open", group: "navigation" as const },
          { id: "copy_id", group: "sharing" as const },
          { id: "copy_url", group: "sharing" as const },
          { id: "share", group: "sharing" as const },
          { id: "edit_presentation", group: "management" as const },
          { id: "report", group: "support" as const },
        ],
      })),
    },
  };
}
export async function loadCatalogOwnerEditor() {
  throw new Error("unavailable in Storybook");
}

export async function loadTechnologyOwnerEditor() {
  return {
    csrfToken: "storybook",
    members: [],
    presentation: {
      name: "Example",
      description: "",
      avatar_asset_id: null,
      avatar_url: null,
      links: [],
      media: [],
      revision: 0,
      authorization_revision: 0,
      can_edit: true,
      owner: null,
      author: null,
      owner_account_id: null,
      leads: [],
      teams: [],
      projects: [],
      technologies: [],
      components: [],
    },
  };
}

export async function loadCorporateGrantDialog() {
  return {
    csrfToken: "storybook",
    organizationId: "organization_example",
    authorizationRevision: 0,
    members: [],
    initialMemberIds: [],
    initialScope: undefined,
    roles: [],
    grantableRoleNames: [],
    teams: [],
    projects: [],
    capabilities: [],
    definitions: [],
    scopeOptions: [],
  };
}
