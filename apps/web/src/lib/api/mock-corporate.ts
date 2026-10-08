/* eslint-disable max-lines, max-lines-per-function, complexity, @typescript-eslint/no-non-null-assertion, @typescript-eslint/no-unnecessary-type-assertion, @typescript-eslint/no-unused-vars */
/** Offline fixtures only. Dispatch exclusively from the existing mock transport. */
import { z } from "zod";
import { errorBody } from "@/mocks/fixtures";
import fixtureData from "@/mocks/corporate-overview-fixture";
import {
  FIXTURE_COMPONENT_ID,
  FIXTURE_SETUP_ID,
  SEED_A1_AGENT_ID,
  SEED_A1_HOOK_ID,
  SEED_A1_INCIDENT_AGENT_ID,
  SEED_A1_INCIDENT_SETUP_ID,
  SEED_A1_MCP_ID,
  SEED_A1_SETUP_ID,
  SEED_A1_SKILL_CORE_ID,
  SEED_A1_SKILL_PAIR_ID,
  SEED_A2_AGENT_ID,
  SEED_A2_HOOK_ID,
  SEED_A2_MCP_ID,
  SEED_A2_SETUP_ID,
  SEED_A2_SKILL_CORE_ID,
  SEED_A3_SETUP_ID,
} from "@/mocks/fixtures/catalog-ids";
import { entityProfileViewSchema } from "@/lib/corporate-detail";
import type {
  AreaView,
  CorporateOverview,
  CorporateContext,
  CorporateTeamView,
  CorporateProjectView,
  CorporateMember,
  CorporateInvitation,
  CorporateBinding,
  CorporateEffectivePermission,
  CorporateMemberAccess,
  CorporateMemberPrivateGrant,
  CorporateDelegationView,
  CorporatePermissionGrant,
  CorporatePermissionMatrix,
  CorporatePermissionDefinition,
  CorporateRoleView,
  CorporateServicePrincipalView,
  TechnologyView,
  ProjectTeamView,
  ProjectTechnologyView,
  EmployeeTechnologyView,
  CategoryView,
  CorporateCatalogAssignment,
  CorporateDirectoryItem,
  CorporateDirectoryReference,
  DashboardQuery,
  DashboardView,
  TechnologyMappingEntry,
  TechnologyMappingView,
  TechnologyScanListEntry,
  TechnologyUnmappedEntry,
} from "./generated/types.gen";
import type { WorkspaceMockResult } from "./mock-workspace";

const fixture = fixtureData as { cases: Array<{ body: CorporateOverview }> };

const graph = fixture.cases[0]?.body as CorporateOverview;
const organization = graph.organization;
const employeeNodes = graph.nodes.filter((item) => item.kind === "employee");
const teamNodes = graph.nodes.filter((item) => item.kind === "team");
const projectNodes = graph.nodes.filter((item) => item.kind === "project");
const descriptions = new Map([
  ["Platform", "Core platform services and shared engineering capabilities."],
  ["Growth Experiments", "Drive user growth through experimental products and features."],
  ["Twinby Dating Core", "Core platform for the Twinby dating service."],
  ["Core", "A cross-functional product engineering team."],
  ["Product & Engineering", "Build and iterate on growth features."],
  ["Customer Success", "User support and success operations."],
  ["Platform Engineering", "Infrastructure, tooling and platform services."],
  ["Data Platform", "Data infrastructure and experimentation."],
]);
const roles = [
  "team_lead",
  "project_lead",
  "engineering_lead",
  "ml_engineer",
  "data_analyst",
  "research_engineer",
  "project_lead",
  "support_lead",
  "platform_lead",
  "support_specialist",
  "support_engineer",
  "devops_engineer",
  "platform_engineer",
  "data_engineer",
];
const members: CorporateMember[] = employeeNodes.map((item, index) => ({
  schema_version: 1,
  account_id: item.id,
  display_name: item.name,
  state: "active",
  role: roles[index] ?? "staff",
  job_title_id: null,
  job_title_name: null,
  contact_email: index % 4 === 3 ? null : `member${index + 1}@corp.example`,
  joined_at: new Date(Date.UTC(2026, 4, 12 + index)).toISOString(),
  last_activity_at: new Date(Date.now() - (index + 1) * 3_600_000).toISOString(),
  revision: 1,
  available_actions: [],
}));
const memberDescriptions = [
  "Corporate team lead for the shared Core platform.",
  "Project lead coordinating product delivery and growth experiments.",
  "Engineering lead focused on applied machine learning.",
  "ML engineer building experimentation and recommendation systems.",
  "Data analyst translating product signals into decisions.",
  "Research engineer supporting product discovery and evaluation.",
  "Project lead for the Twinby Dating Core program.",
  "Support lead for customer success operations.",
  "Platform lead responsible for infrastructure reliability.",
  "Support specialist helping customers resolve issues quickly.",
  "Support engineer owning technical incident resolution.",
  "DevOps engineer automating delivery and observability.",
  "Platform engineer maintaining shared runtime services.",
  "Data engineer maintaining analytics pipelines and storage.",
];
members.forEach((item, index) =>
  descriptions.set(
    item.display_name ?? "",
    memberDescriptions[index] ?? "Corporate engineering team member.",
  ),
);
const memberById = new Map(members.map((item) => [item.account_id, item]));
// Standalone bundles this module into two module realms (page render and
// /api routes). Mutable mock state must live on globalThis or a mutation in
// one realm stays invisible to a read in the other.
const builtInRoles = new Set(["staff", "lead", "superadmin"]);
const initialRoleViews: CorporateRoleView[] = [
  {
    schema_version: 1,
    name: "staff",
    parent_role: null,
    permissions: [
      "member.list",
      "member.read",
      "project.list",
      "project.read",
      "team.list",
      "technology.list",
      "technology.read",
    ],
    revision: 1,
  },
  {
    schema_version: 1,
    name: "lead",
    parent_role: "staff",
    permissions: ["member.update", "member.invite", "project.update", "team.read", "team.update"],
    revision: 1,
  },
  {
    schema_version: 1,
    name: "superadmin",
    parent_role: "lead",
    permissions: [
      "binding.create",
      "binding.delete",
      "binding.list",
      "member.create",
      "member.delete",
      "member.manage",
      "organization.manage",
      "role.create",
      "role.delete",
      "role.list",
      "role.update",
      "service_principal.list",
      "service_principal.manage",
      "audit.list",
    ],
    revision: 1,
  },
  {
    schema_version: 1,
    name: "platform_auditor",
    parent_role: "staff",
    permissions: ["audit.export", "audit.list"],
    revision: 1,
  },
];
const initMockState = () => ({
  invitations: [
    {
      schema_version: 1,
      invitation_id: "invitation_0001",
      issuer_account_id: employeeNodes[0]?.id ?? null,
      organization_id: organization.organization_id,
      recipient_email: "new.joiner@corp.example",
      display_name: "New Joiner",
      role: "staff",
      team_ids: [],
      project_ids: [],
      job_title_id: null,
      accepted_account_id: null,
      claimant_account_id: null,
      state: "pending",
      delivery_state: "sent",
      delivery_error: null,
      created_at: new Date(Date.now() - 12 * 3_600_000).toISOString(),
      expires_at: new Date(Date.now() + 84 * 3_600_000).toISOString(),
      token: null,
    },
    {
      schema_version: 1,
      invitation_id: "invitation_0002",
      issuer_account_id: employeeNodes[0]?.id ?? null,
      organization_id: organization.organization_id,
      recipient_email: "revoked@corp.example",
      display_name: "Revoked Invite",
      role: "lead",
      team_ids: [],
      project_ids: [],
      job_title_id: null,
      accepted_account_id: null,
      claimant_account_id: null,
      state: "revoked",
      delivery_state: "failed",
      delivery_error: "550 mailbox unavailable",
      created_at: new Date(Date.now() - 5 * 24 * 3_600_000).toISOString(),
      expires_at: new Date(Date.now() - 2 * 24 * 3_600_000).toISOString(),
      token: null,
    },
  ] as CorporateInvitation[],
  policy: { allowed_email_domains: [] as string[], authorization_revision: 1 },
  roles: [...initialRoleViews] as CorporateRoleView[],
  bindings: [
    {
      schema_version: 1,
      binding_id: "binding_0000000000000000001",
      account_id: members[0]!.account_id,
      service_principal_id: null,
      principal_type: "user",
      role: "superadmin",
      scope_kind: "organization",
      scope_id: organization.organization_id,
      state: "active",
      revision: 1,
      origin: "membership",
      coverage: "descendants",
    },
    {
      schema_version: 1,
      binding_id: "binding_0000000000000000002",
      account_id: members[1]?.account_id ?? "",
      service_principal_id: null,
      principal_type: "user",
      role: "lead",
      scope_kind: "team",
      scope_id: teamViews[0]?.team_id ?? "team_unknown",
      state: "active",
      revision: 1,
      origin: "assignment",
      coverage: "self",
    },
    {
      schema_version: 1,
      binding_id: "binding_0000000000000000003",
      account_id: members[2]?.account_id ?? "",
      service_principal_id: null,
      principal_type: "user",
      role: "staff",
      scope_kind: "project",
      scope_id: projectViews[0]?.project_id ?? "project_unknown",
      state: "active",
      revision: 1,
      origin: "direct",
      coverage: "self",
    },
  ] as CorporateBinding[],
  grants: [
    {
      schema_version: 1,
      grant_id: "grant_0000000000000000001",
      account_id: members[3]?.account_id ?? "",
      service_principal_id: null,
      principal_type: "user",
      permission: "technology.update",
      scope_kind: "technology",
      scope_id: technologies[0]?.technology_id ?? "technology_unknown",
      state: "active",
      issuer_account_id: members[0]!.account_id,
      revision: 1,
    },
  ] as CorporatePermissionGrant[],
  servicePrincipals: [
    {
      schema_version: 1,
      service_principal_id: "service_principal_0000000000000001",
      organization_id: organization.organization_id,
      name: "telemetry-ingest",
      state: "active",
      revision: 1,
      binding: {
        schema_version: 1,
        binding_id: "binding_0000000000000000099",
        account_id: null,
        service_principal_id: "service_principal_0000000000000001",
        principal_type: "service_principal",
        role: "staff",
        scope_kind: "organization",
        scope_id: organization.organization_id,
        state: "active",
        revision: 1,
        origin: "service_principal",
        coverage: "self",
      },
    },
  ] as CorporateServicePrincipalView[],
});
const graphEdges = graph.edges;
const teamMembers = (teamId: string) =>
  graphEdges
    .filter((edge) => edge.kind === "team_employee" && edge.parent_id === teamId)
    .map((edge) => memberById.get(edge.child_id))
    .filter((item): item is CorporateMember => Boolean(item));
const teamViews: CorporateTeamView[] = teamNodes.map((item) => ({
  schema_version: 1,
  team_id: item.id,
  organization_id: organization.organization_id,
  name: item.name,
  description: descriptions.get(item.name) ?? `Offline ${item.name} team fixture`,
  state: "active",
  revision: 1,
  lead_account_ids: item.lead_account_ids,
  members: teamMembers(item.id),
  project_ids: [],
  technology_ids: [],
  assignments: [],
  effective_assignments: [],
  effective_permissions: [],
  available_actions: [],
  governance_history: [],
  owned_catalog_objects: [],
  maintained_catalog_objects: [],
}));
const projectViews: CorporateProjectView[] = projectNodes.map((item, index) => ({
  schema_version: 1,
  project_id: item.id,
  organization_id: organization.organization_id,
  name: item.name,
  state: "active",
  lifecycle: "active",
  revision: 1,
  repository_activity_at: null,
  source_availability: "unknown",
  repositories:
    index === 0
      ? [
          {
            provider: "github" as const,
            provider_project_id: "group/offline-service",
            repository_url: "https://git.example.test/group/offline-service",
            namespace: "group",
            default_branch: "main",
            observed_at: null,
            observed_revision: null,
          },
        ]
      : [],
  available_actions: [],
}));
const member = members[0]!;
const technologySpecs = [
  ["technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z", "Offline technology", "Runtime"],
  ["technology_01JQZK7B8N4M6P2R9T5V0X3Y1A", "Python", "Language"],
  ["technology_01JQZK7B8N4M6P2R9T5V0X3Y2B", "PostgreSQL", "Database"],
  ["technology_01JQZK7B8N4M6P2R9T5V0X3Y3C", "Kubernetes", "Infrastructure"],
  ["technology_01JQZK7B8N4M6P2R9T5V0X3Y4D", "Terraform", "Infrastructure"],
  ["technology_01JQZK7B8N4M6P2R9T5V0X3Y5E", "AWS", "Cloud platform"],
  ["technology_01JQZK7B8N4M6P2R9T5V0X3Y6F", "ClickHouse", "Database"],
  ["technology_01JQZK7B8N4M6P2R9T5V0X3Y8H", "Redis", "Database"],
  ["technology_01JQZK7B8N4M6P2R9T5V0X3Y9J", "Kafka", "Messaging"],
  ["technology_01JQZK7B8N4M6P2R9T5V0X3YAK", "Datadog", "Observability"],
] as const;
const categoryViews: CategoryView[] = [
  ...new Map(
    technologySpecs.map(([, , name], index) => [
      name,
      {
        category_id: `category_01JQZK7B8N4M6P2R9T5V0X3Y${String(index + 1).padStart(2, "0")}`,
        area_id: null,
        description: `${name} technologies`,
        name,
        provenance: "offline-fixture",
        revision: 1,
        state: "active",
      } satisfies CategoryView,
    ]),
  ).values(),
];
const categoryId = new Map(categoryViews.map((item) => [item.name, item.category_id]));
const areaViews: AreaView[] = [
  {
    area_id: "area_01JQZK7B8N4M6P2R9T5V0X3Y01",
    organization_id: organization.organization_id,
    name: "Data platform",
    description: "Storage, databases and data pipelines.",
    provenance: "offline-fixture",
    revision: 1,
    state: "active",
  },
];
const mockScanEntries: TechnologyScanListEntry[] = [];
const technologies: TechnologyView[] = technologySpecs.map(([id, name, category]) => ({
  schema_version: 1,
  technology_id: id,
  organization_id: organization.organization_id,
  owner_account_id: member.account_id,
  name,
  description: descriptions.get(name) ?? `${name} used across the corporate engineering fixture.`,
  aliases: [],
  category_ids: [categoryId.get(category) ?? ""].filter(Boolean),
  official_urls: [],
  icon_url: null,
  lifecycle: "active",
  restore_lifecycle: "active",
  redirect_id: null,
  revision: 1,
  provenance: "manual",
  available_actions: [],
}));

const mockState = ((globalThis as Record<string, unknown>).__aiStpCorporateMock ??=
  initMockState()) as ReturnType<typeof initMockState>;
const mockInvitations = mockState.invitations;
const mockPolicy = mockState.policy;
const mockRoles = mockState.roles;
const mockBindings = mockState.bindings;
const mockGrants = mockState.grants;
const mockServicePrincipals = mockState.servicePrincipals;
const technologyById = new Map(technologies.map((item) => [item.technology_id, item]));
// Server actions and page renders can load separate module instances (dev
// compilers, per-entry server chunks); hoist mutable review state so every
// instance observes the same queue.
const sharedMockState = globalThis as {
  __aiStpMockUnmapped?: TechnologyUnmappedEntry[];
  __aiStpMockMappings?: TechnologyMappingView[];
};
const unmappedCoordinates: TechnologyUnmappedEntry[] = (sharedMockState.__aiStpMockUnmapped ??= [
  {
    kind: "package",
    coordinate: "package:github.com/jackc/pgx/v5",
    candidate_technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y2B",
    resolved_technology_id: null,
    project_ids: [projectViews[0]!.project_id],
    state: "open",
  },
  {
    kind: "package",
    coordinate: "package:github.com/pressly/goose/v3",
    candidate_technology_id: null,
    resolved_technology_id: null,
    project_ids: [projectViews[0]!.project_id, projectViews[1]!.project_id],
    state: "open",
  },
  {
    kind: "image",
    coordinate: "image:harbor.internal/goose-migrations:v3.24",
    candidate_technology_id: null,
    resolved_technology_id: null,
    project_ids: [projectViews[0]!.project_id],
    state: "open",
  },
  {
    kind: "package",
    coordinate: "package:github.com/ogen-go/ogen",
    candidate_technology_id: null,
    resolved_technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    project_ids: [projectViews[2]!.project_id],
    state: "resolved",
  },
]);
const mappingSnapshots: TechnologyMappingView[] = (sharedMockState.__aiStpMockMappings ??= [
  {
    digest: "sha256:fixture-mapping-v1",
    entries: [
      {
        coordinate: "package:github.com/ogen-go/ogen",
        kind: "package",
        provenance: "review",
        technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
      },
    ],
    organization_id: organization.organization_id,
    version: "mapping-fixture-1",
  },
]);
const projectTeamPairs = [
  [projectViews[0]!.project_id, teamViews[0]!.team_id, "owner"],
  [projectViews[1]!.project_id, teamViews[1]!.team_id, "owner"],
  [projectViews[1]!.project_id, teamViews[4]!.team_id, "contributor"],
  [projectViews[2]!.project_id, teamViews[3]!.team_id, "owner"],
  [projectViews[2]!.project_id, teamViews[2]!.team_id, "contributor"],
] as const;
const projectTeamRelations: ProjectTeamView[] = projectTeamPairs.flatMap(
  ([projectId, teamId, role]) => [
    {
      organization_id: organization.organization_id,
      project_id: projectId,
      relation_id: `${projectId}:team:${teamId}`,
      revision: 1,
      role,
      state: "current",
      team_id: teamId,
    } satisfies ProjectTeamView,
  ],
);
const projectTechPairs = [
  [projectViews[0]!.project_id, technologySpecs[0]![0]],
  [projectViews[1]!.project_id, technologySpecs[1]![0]],
  [projectViews[1]!.project_id, technologySpecs[2]![0]],
  [projectViews[2]!.project_id, technologySpecs[3]![0]],
  [projectViews[2]!.project_id, technologySpecs[4]![0]],
  [projectViews[2]!.project_id, technologySpecs[5]![0]],
  [projectViews[2]!.project_id, technologySpecs[6]![0]],
  [projectViews[1]!.project_id, technologySpecs[7]![0]],
  [projectViews[2]!.project_id, technologySpecs[8]![0]],
  [projectViews[2]!.project_id, technologySpecs[9]![0]],
] as const;
const projectTechnologyRelations: ProjectTechnologyView[] = projectTechPairs.flatMap(
  ([projectId, technologyId]) => [
    {
      facts: [
        {
          context: "production",
          evidence: [],
          freshness: "unknown",
          review: "confirmed",
          version: null,
          version_kind: "unknown",
        },
      ],
      organization_id: organization.organization_id,
      project_id: projectId,
      relation_id: `${projectId}:technology:${technologyId}`,
      revision: 1,
      state: "current",
      technology_id: technologyId,
    } satisfies ProjectTechnologyView,
  ],
);
const employeeTechnologyRelations: EmployeeTechnologyView[] = [
  {
    account_id: members[1]!.account_id,
    organization_id: organization.organization_id,
    relation_id: `${members[1]!.account_id}:technology:${technologySpecs[1]![0]}`,
    revision: 1,
    schema_version: 1,
    state: "current",
    technology_id: technologySpecs[1]![0],
  },
  {
    account_id: members[2]!.account_id,
    organization_id: organization.organization_id,
    relation_id: `${members[2]!.account_id}:technology:${technologySpecs[1]![0]}`,
    revision: 1,
    schema_version: 1,
    state: "current",
    technology_id: technologySpecs[1]![0],
  },
  {
    account_id: members[3]!.account_id,
    organization_id: organization.organization_id,
    relation_id: `${members[3]!.account_id}:technology:${technologySpecs[2]![0]}`,
    revision: 1,
    schema_version: 1,
    state: "current",
    technology_id: technologySpecs[2]![0],
  },
  {
    account_id: members[4]!.account_id,
    organization_id: organization.organization_id,
    relation_id: `${members[4]!.account_id}:technology:${technologySpecs[0]![0]}`,
    revision: 1,
    schema_version: 1,
    state: "current",
    technology_id: technologySpecs[0]![0],
  },
];
const overviewGraph: CorporateOverview = {
  ...graph,
  nodes: graph.nodes.map((node) => ({
    ...node,
    technologies:
      node.kind === "project"
        ? projectTechnologyRelations
            .filter((relation) => relation.project_id === node.id)
            .map((relation) => technologyById.get(relation.technology_id))
            .filter((item): item is TechnologyView => Boolean(item))
            .map((item) => ({ kind: "technology", id: item.technology_id, name: item.name }))
        : node.kind === "employee"
          ? employeeTechnologyRelations
              .filter((relation) => relation.account_id === node.id)
              .map((relation) => technologyById.get(relation.technology_id))
              .filter((item): item is TechnologyView => Boolean(item))
              .map((item) => ({ kind: "technology", id: item.technology_id, name: item.name }))
          : [],
  })),
};
const technologyTeams = new Map<string, string[]>([
  [technologySpecs[0][0], [teamViews[0]?.team_id ?? "", teamViews[1]?.team_id ?? ""]],
  [technologySpecs[1][0], [teamViews[1]?.team_id ?? ""]],
  [technologySpecs[2][0], [teamViews[1]?.team_id ?? ""]],
  [technologySpecs[3][0], [teamViews[3]?.team_id ?? ""]],
  [technologySpecs[4][0], [teamViews[3]?.team_id ?? ""]],
  [technologySpecs[5][0], [teamViews[3]?.team_id ?? ""]],
  [technologySpecs[6][0], [teamViews[4]?.team_id ?? ""]],
]);
// This fixture projection is not evidence of production RBAC enforcement.
const capabilities = [
  "team.list",
  "team.create",
  "team.read",
  "team.update",
  "team.delete",
  "project.list",
  "project.read",
  "project.create",
  "project.update",
  "project.delete",
  "member.read",
  "member.create",
  "member.update",
  "member.delete",
  "member.manage",
  "member.invite",
  "member.list",
  "organization.read",
  "organization.manage",
  "role.list",
  "role.create",
  "role.read",
  "role.update",
  "role.delete",
  "binding.list",
  "binding.create",
  "binding.read",
  "binding.update",
  "binding.delete",
  "service_principal.list",
  "service_principal.read",
  "service_principal.manage",
  "service_principal.delete",
  "audit.list",
  "audit.export",
  "job_title.list",
  "technology.list",
  "technology.read",
  "technology.update",
  "project_team.list",
  "project_team.read",
  "project_technology.list",
  "project_technology.read",
  "technology_team.list",
  "technology_team.read",
  "category.list",
  "category.read",
  "category.create",
  "category.update",
  "technology_decision.read",
  "telemetry.read",
];
const context: CorporateContext = {
  schema_version: 1,
  organization,
  member,
  teams: teamViews,
  projects: projectViews,
  bindings: mockBindings.filter((item) => item.account_id === member.account_id),
  capabilities,
};
const dashboardViews: DashboardView[] = [];
type CorporateResource = {
  id: string;
  name: string;
  kind: "team" | "project" | "employee" | "technology";
  detail: CorporateTeamView | CorporateProjectView | CorporateMember | TechnologyView;
};
const resources: Record<"teams" | "projects" | "members" | "technologies", CorporateResource[]> = {
  teams: teamViews.map((detail) => ({
    id: detail.team_id,
    name: detail.name,
    kind: "team",
    detail,
  })),
  projects: projectViews.map((detail) => ({
    id: detail.project_id,
    name: detail.name,
    kind: "project",
    detail,
  })),
  members: members.map((detail) => ({
    id: detail.account_id,
    name: detail.display_name ?? detail.account_id,
    kind: "employee",
    detail,
  })),
  technologies: technologies.map((detail) => ({
    id: detail.technology_id,
    name: detail.name,
    kind: "technology",
    detail,
  })),
};
const resourceEntries = () =>
  Object.entries(resources) as [keyof typeof resources, CorporateResource[]][];
const resourceFor = (kind: CorporateResource["kind"], id: string) =>
  resourceEntries()
    .flatMap(([, items]) => items)
    .find((item) => item.kind === kind && item.id === id);
type Profile = z.infer<typeof entityProfileViewSchema>;
type CorporateUploadReceipt = {
  schema_version: 1;
  avatar_asset_id: string;
  media_id: string;
  public_url: string;
  kind: "image" | "video";
  state: "ready";
  size_bytes: number;
};
type CorporateMockUpload = {
  body: Uint8Array;
  contentType: string;
  receipt: CorporateUploadReceipt;
};
const store = globalThis as typeof globalThis & {
  __aiStpCorporateTestProfiles?: Map<string, Profile>;
  __aiStpCorporateTestReceipts?: Map<string, { effect: string; result: Profile }>;
  __aiStpCorporateTestUploads?: Map<string, CorporateMockUpload>;
  __aiStpCorporateTestUploadReceipts?: Map<
    string,
    { effect: string; result: CorporateUploadReceipt }
  >;
};
const profiles = (store.__aiStpCorporateTestProfiles ??= new Map());
const receipts = (store.__aiStpCorporateTestReceipts ??= new Map());
// Synthetic offline fixtures only; live persisted assets remain API-owned.
const uploads = (store.__aiStpCorporateTestUploads ??= new Map());
const uploadReceipts = (store.__aiStpCorporateTestUploadReceipts ??= new Map());

function readHeader(headers: HeadersInit | undefined, name: string): string | null {
  if (headers instanceof Headers) return headers.get(name);
  if (headers && typeof headers === "object" && !Array.isArray(headers)) {
    return headers[name] ?? headers[name.toLowerCase()] ?? null;
  }
  return null;
}

const writeSchema = z.object({
  schema_version: z.literal(1),
  fields: entityProfileViewSchema.shape.fields,
  expected_revision: z.number().int(),
  authorization_revision: z.literal(1),
  idempotency_key: z.string().uuid(),
});
const ok = (body: unknown): WorkspaceMockResult => ({ status: 200, body });
const error = (status: number, code: string): WorkspaceMockResult => ({
  status,
  body: errorBody(code, "corporate.offline"),
});
const list = (items: unknown[]) => ({ schema_version: 1, items, total: items.length });

function avatarDataUrl(name: string): string {
  const avatarIds = [583231, 1024025, 810438, 170270, 25254, 499550, 1500684, 6764957];
  const seed = Array.from(name).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return `https://avatars.githubusercontent.com/u/${avatarIds[seed % avatarIds.length]}?v=4`;
}

function initialProfile(item: CorporateResource): Profile {
  return {
    name: item.name,
    revision: 0,
    can_edit: true,
    avatar_url: item.kind === "employee" ? avatarDataUrl(item.name) : null,
    owner_account_id: item.kind === "technology" ? member.account_id : null,
    fields: {
      description: descriptions.get(item.name) ?? `Offline **${item.kind}** fixture`,
      avatar_asset_id: null,
      links: [],
      media: [],
    },
  };
}

function uploadBytes(body: unknown): Uint8Array | null {
  if (body instanceof ArrayBuffer) return new Uint8Array(body);
  if (ArrayBuffer.isView(body))
    return new Uint8Array(body.buffer, body.byteOffset, body.byteLength);
  return null;
}

function fixtureAssetId(seed: string): string {
  return `avatar_${fixtureDigest(seed).slice(0, 24)}`;
}

// ponytail: deterministic browser-only fixture fingerprint; cryptographic
// hashing belongs to the API and this mock never authenticates the value.
function fixtureDigest(value: string | Uint8Array): string {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : value;
  let hash = 2166136261;
  for (const byte of bytes) hash = Math.imul(hash ^ byte, 16777619);
  return (hash >>> 0).toString(16).padStart(8, "0").repeat(8);
}

const uploadQuerySchema = z.object({
  purpose: z.enum(["avatar", "media"]),
  expected_revision: z.string().regex(/^\d+$/).transform(Number).pipe(z.number().int().safe()),
  authorization_revision: z
    .string()
    .regex(/^[1-9]\d*$/)
    .transform(Number)
    .pipe(z.number().int().safe()),
});

function corporateMediaUploadHandler(
  method: string,
  body: unknown,
  query: URLSearchParams,
  headers: HeadersInit | undefined,
  item: CorporateResource,
): WorkspaceMockResult {
  if (method !== "POST") return error(405, "AI_STP_VALIDATION_ERROR");
  const parsed = uploadQuerySchema.safeParse(Object.fromEntries(query));
  const key = readHeader(headers, "Idempotency-Key") ?? "";
  const contentType = readHeader(headers, "Content-Type")?.toLowerCase() ?? "";
  if (!parsed.success || !/^[A-Za-z0-9._~-]{16,128}$/.test(key) || !contentType)
    return error(422, "AI_STP_VALIDATION_ERROR");
  if (parsed.data.authorization_revision !== 1) return error(412, "AI_STP_PRECONDITION_FAILED");
  const bytes = uploadBytes(body);
  if (!bytes?.byteLength) return error(400, "AI_STP_VALIDATION_ERROR");
  const isAvatar = parsed.data.purpose === "avatar";
  const allowed = isAvatar
    ? ["image/png", "image/jpeg", "image/webp"]
    : ["image/png", "image/jpeg", "image/webp", "image/gif", "video/mp4", "video/webm"];
  if (!allowed.includes(contentType)) return error(422, "AI_STP_VALIDATION_ERROR");
  const profileSuffix = `entity-profiles/${item.kind}/${item.id}`;
  const current = profiles.get(profileSuffix) ?? initialProfile(item);
  const fingerprint = JSON.stringify({
    purpose: parsed.data.purpose,
    expected_revision: parsed.data.expected_revision,
    authorization_revision: parsed.data.authorization_revision,
    content_type: contentType,
    digest: fixtureDigest(bytes),
  });
  const receiptKey = `${profileSuffix}:${key}`;
  const previous = uploadReceipts.get(receiptKey);
  if (previous)
    return previous.effect === fingerprint ? ok(previous.result) : error(409, "AI_STP_CONFLICT");
  if (parsed.data.expected_revision !== current.revision) return error(409, "AI_STP_CONFLICT");
  const assetId = fixtureAssetId(receiptKey);
  const receipt: CorporateUploadReceipt = {
    schema_version: 1,
    avatar_asset_id: assetId,
    media_id: assetId,
    public_url: `/v1/media/avatars/${assetId}`,
    kind: contentType.startsWith("video/") ? "video" : "image",
    state: "ready",
    size_bytes: bytes.byteLength,
  };
  uploads.set(assetId, { body: bytes.slice(), contentType, receipt });
  uploadReceipts.set(receiptKey, { effect: fingerprint, result: receipt });
  return ok(receipt);
}

export function readMockCorporateMedia(assetId: string) {
  const upload = uploads.get(assetId);
  return upload ? { body: upload.body.slice(), contentType: upload.contentType } : null;
}

function hydrateProfileAvatar(profile: Profile): Profile {
  const assetId = profile.fields.avatar_asset_id;
  return {
    ...profile,
    avatar_url: assetId ? (uploads.get(assetId)?.receipt.public_url ?? null) : profile.avatar_url,
  };
}

function corporateProfileHandler(
  method: string,
  suffix: string,
  body: unknown,
  item: CorporateResource,
): WorkspaceMockResult {
  const initial = initialProfile(item);
  const current = profiles.get(suffix) ?? initial;
  if (method === "GET") {
    return ok(hydrateProfileAvatar(current));
  }
  if (method !== "PUT") return error(405, "AI_STP_VALIDATION_ERROR");
  const parsed = writeSchema.safeParse(body);
  if (!parsed.success) return error(422, "AI_STP_VALIDATION_ERROR");
  const { idempotency_key: key, ...effect } = parsed.data;
  const fingerprint = JSON.stringify(effect);
  const receiptKey = `${suffix}:${key}`;
  const receipt = receipts.get(receiptKey);
  if (receipt)
    return receipt.effect === fingerprint ? ok(receipt.result) : error(409, "AI_STP_CONFLICT");
  if (effect.expected_revision !== current.revision) return error(409, "AI_STP_CONFLICT");
  const result = hydrateProfileAvatar(
    entityProfileViewSchema.parse({
      ...current,
      avatar_url: effect.fields.avatar_asset_id ? current.avatar_url : null,
      fields: effect.fields,
      revision: current.revision + 1,
    }),
  );
  profiles.set(suffix, result);
  receipts.set(receiptKey, { effect: fingerprint, result });
  return ok(result);
}

function corporateDirectoryResponse(query: URLSearchParams): WorkspaceMockResult {
  const resource = query.get("resource") as keyof typeof resources | null;
  if (!resource || !["projects", "teams", "members", "technologies"].includes(resource))
    return error(422, "AI_STP_VALIDATION_ERROR");
  const source = resources[resource];
  const ref = (kind: CorporateDirectoryReference["kind"], id: string, name: string) => ({
    id,
    kind,
    name,
  });
  const teamRef = (id: string) => {
    const item = teamViews.find((candidate) => candidate.team_id === id);
    return item ? ref("team", item.team_id, item.name) : null;
  };
  const projectRef = (id: string) => {
    const item = projectViews.find((candidate) => candidate.project_id === id);
    return item ? ref("project", item.project_id, item.name) : null;
  };
  const memberRef = (id: string) => {
    const item = memberById.get(id);
    return item ? ref("employee", item.account_id, item.display_name ?? item.account_id) : null;
  };
  const technologyRef = (id: string) => {
    const item = technologyById.get(id);
    return item ? ref("technology", item.technology_id, item.name) : null;
  };
  const leadTeamIdsByMember = new Map<string, Set<string>>();
  for (const team of teamViews) {
    for (const accountId of team.lead_account_ids) {
      const teamIds = leadTeamIdsByMember.get(accountId) ?? new Set<string>();
      teamIds.add(team.team_id);
      leadTeamIdsByMember.set(accountId, teamIds);
    }
  }
  const cards: CorporateDirectoryItem[] = source.map((item) => {
    const teams =
      resource === "members"
        ? teamViews.filter((candidate) =>
            candidate.members.some((candidateMember) => candidateMember.account_id === item.id),
          )
        : resource === "technologies"
          ? (technologyTeams.get(item.id) ?? [])
              .map((id) => teamViews.find((candidate) => candidate.team_id === id))
              .filter((candidate): candidate is CorporateTeamView => Boolean(candidate))
          : resource === "teams"
            ? [teamViews.find((candidate) => candidate.team_id === item.id)].filter(
                (candidate): candidate is CorporateTeamView => Boolean(candidate),
              )
            : projectTeamRelations
                .filter((relation) => relation.project_id === item.id)
                .map((relation) =>
                  teamViews.find((candidate) => candidate.team_id === relation.team_id),
                )
                .filter((candidate): candidate is CorporateTeamView => Boolean(candidate));
    const projects =
      resource === "projects"
        ? [projectViews.find((candidate) => candidate.project_id === item.id)].filter(
            (candidate): candidate is CorporateProjectView => Boolean(candidate),
          )
        : resource === "teams"
          ? projectTeamRelations
              .filter((relation) => relation.team_id === item.id)
              .map((relation) =>
                projectViews.find((candidate) => candidate.project_id === relation.project_id),
              )
              .filter((candidate): candidate is CorporateProjectView => Boolean(candidate))
          : resource === "technologies"
            ? projectTechnologyRelations
                .filter((relation) => relation.technology_id === item.id)
                .map((relation) =>
                  projectViews.find((candidate) => candidate.project_id === relation.project_id),
                )
                .filter((candidate): candidate is CorporateProjectView => Boolean(candidate))
            : teams.flatMap((candidate) =>
                candidate.members.some((candidateMember) => candidateMember.account_id === item.id)
                  ? projectTeamRelations
                      .filter((relation) => relation.team_id === candidate.team_id)
                      .map((relation) =>
                        projectViews.find(
                          (projectCandidate) => projectCandidate.project_id === relation.project_id,
                        ),
                      )
                      .filter((candidate): candidate is CorporateProjectView => Boolean(candidate))
                  : [],
              );
    const technologiesFor =
      resource === "projects"
        ? projectTechnologyRelations
            .filter((relation) => relation.project_id === item.id)
            .map((relation) => technologyById.get(relation.technology_id))
            .filter((candidate): candidate is TechnologyView => Boolean(candidate))
        : resource === "members"
          ? employeeTechnologyRelations
              .filter((relation) => relation.account_id === item.id)
              .map((relation) => technologyById.get(relation.technology_id))
              .filter((candidate): candidate is TechnologyView => Boolean(candidate))
          : resource === "teams"
            ? [...technologyTeams.entries()]
                .filter(([, teamIds]) => teamIds.includes(item.id))
                .map(([technologyId]) => technologyById.get(technologyId))
                .filter((candidate): candidate is TechnologyView => Boolean(candidate))
            : [];
    const leadIds =
      resource === "teams"
        ? (item.detail as CorporateTeamView).lead_account_ids
        : teams.flatMap((candidate) => candidate.lead_account_ids);
    const leads = leadIds
      .map((id) => memberById.get(id))
      .filter((candidate): candidate is CorporateMember => Boolean(candidate));
    const ownerTeam = teams[0] ? teamRef(teams[0].team_id) : null;
    const owner =
      resource === "technologies" && teams[0]?.lead_account_ids[0]
        ? memberRef(teams[0].lead_account_ids[0])
        : null;
    return {
      id: item.id,
      name: item.name,
      kind:
        resource === "members"
          ? "employee"
          : resource === "technologies"
            ? "technology"
            : resource === "teams"
              ? "team"
              : "project",
      description: descriptions.get(item.name) ?? `Offline ${item.kind} fixture`,
      revision: 1,
      role: resource === "members" ? (item.detail as CorporateMember).role : null,
      job_title: null,
      is_lead:
        resource === "members" &&
        teamViews.some((candidate) => candidate.lead_account_ids.includes(item.id)),
      leads: leads
        .map((candidate) => memberRef(candidate.account_id))
        .filter((candidate): candidate is CorporateDirectoryReference => Boolean(candidate)),
      teams: teams
        .map((candidate) => teamRef(candidate.team_id))
        .filter((candidate): candidate is CorporateDirectoryReference => Boolean(candidate)),
      related_teams: teams
        .map((candidate) => teamRef(candidate.team_id))
        .filter((candidate): candidate is CorporateDirectoryReference => Boolean(candidate)),
      projects: [
        ...new Map(
          projects.map((candidate) => [candidate.project_id, projectRef(candidate.project_id)]),
        ).values(),
      ].filter((candidate): candidate is CorporateDirectoryReference => Boolean(candidate)),
      technologies: technologiesFor
        .map((candidate) => technologyRef(candidate.technology_id))
        .filter((candidate): candidate is CorporateDirectoryReference => Boolean(candidate)),
      categories:
        resource === "technologies"
          ? (item.detail as TechnologyView).category_ids
              .map((id) => categoryViews.find((candidate) => candidate.category_id === id))
              .filter((candidate): candidate is CategoryView => Boolean(candidate))
              .map((candidate) => ref("category", candidate.category_id, candidate.name))
          : [],
      owner_team: ownerTeam,
      owner,
      available_actions: [],
    };
  });
  const filterNames: Record<string, keyof CorporateDirectoryItem> = {
    lead_ids: "leads",
    team_ids: "teams",
    technology_ids: "technologies",
    project_ids: "projects",
    category_ids: "categories",
  };
  const filtered = cards.filter((card) => {
    const q = query.get("query")?.trim().toLowerCase();
    if (q && !`${card.name} ${card.description}`.toLowerCase().includes(q)) return false;
    if (query.get("is_lead") === "true" && !card.is_lead) return false;
    const selectedTeams = query.getAll("team_ids");
    if (
      resource === "members" &&
      query.get("is_lead") === "true" &&
      selectedTeams.length &&
      !selectedTeams.some((id) => leadTeamIdsByMember.get(card.id)?.has(id))
    )
      return false;
    return Object.entries(filterNames).every(([name, field]) => {
      const selected = query.getAll(name);
      const refs = card[field] as CorporateDirectoryReference[];
      return (
        !selected.length ||
        selected.some(
          (id) =>
            refs.some((candidate) => candidate.id === id) ||
            (resource === "members" && card.is_lead && id === card.id),
        )
      );
    });
  });
  const offset = Math.max(0, Number(query.get("offset") ?? 0) || 0);
  const limit = Math.max(1, Number(query.get("limit") ?? 256) || 256);
  const allRefs = (field: keyof CorporateDirectoryItem) => [
    ...new Map(
      cards.flatMap((card) =>
        (card[field] as CorporateDirectoryReference[]).map((candidate) => [
          candidate.id,
          candidate,
        ]),
      ),
    ).values(),
  ];
  return ok({
    schema_version: 1,
    items: filtered.slice(offset, offset + limit),
    total: filtered.length,
    organization,
    resource,
    facets: {
      leads: allRefs("leads"),
      teams: allRefs("teams"),
      technologies: allRefs("technologies"),
      projects: allRefs("projects"),
      categories: allRefs("categories"),
    },
  });
}

function catalogAssignments(
  subjectKind?: string,
  subjectId?: string,
): CorporateCatalogAssignment[] {
  const components: ReadonlyArray<readonly [string, string]> = [
    ["Claude Code", FIXTURE_COMPONENT_ID],
    ["Context7", SEED_A1_SKILL_CORE_ID],
    ["Growth API", SEED_A1_SKILL_PAIR_ID],
    ["Jupyter", SEED_A1_MCP_ID],
    ["MLflow", SEED_A1_HOOK_ID],
    ["Agent Gateway", SEED_A1_AGENT_ID],
    ["Intercom", SEED_A1_INCIDENT_AGENT_ID],
    ["Zendesk", SEED_A2_MCP_ID],
    ["Cluster", SEED_A2_HOOK_ID],
    ["EKS", SEED_A2_AGENT_ID],
    ["Monitoring Agent", SEED_A2_SKILL_CORE_ID],
  ];
  const setups: ReadonlyArray<readonly [string, string]> = [
    ["staging", FIXTURE_SETUP_ID],
    ["production", SEED_A1_SETUP_ID],
    ["research", SEED_A1_INCIDENT_SETUP_ID],
    ["support-staging", SEED_A2_SETUP_ID],
    ["support-production", SEED_A3_SETUP_ID],
  ];
  const subjects = resourceEntries()
    .flatMap(([, items]) => items)
    .filter(
      (item): item is CorporateResource & { kind: "employee" | "team" | "project" } =>
        item.kind !== "technology",
    );
  return subjects.flatMap((subject, subjectIndex) => {
    if (
      (subjectKind &&
        subjectId &&
        !(subject.kind === "employee"
          ? subjectKind === "employee"
          : subject.kind === subjectKind)) ||
      (subjectId && subject.id !== subjectId)
    )
      return [];
    const names =
      subject.kind === "employee"
        ? components.slice(subjectIndex % 4, (subjectIndex % 4) + 2)
        : subject.kind === "team"
          ? components.slice((subjectIndex * 2) % 8, ((subjectIndex * 2) % 8) + 4)
          : components.slice((subjectIndex * 4) % 8, ((subjectIndex * 4) % 8) + 6);
    return [
      ...names.map(([displayName, stableId]) => ({
        displayName,
        kind: "component" as const,
        stableId,
        version: "1.0",
      })),
      ...(subject.kind === "employee"
        ? setups.slice(subjectIndex % 4, (subjectIndex % 4) + 1)
        : setups.slice(0, subject.kind === "team" ? 2 : 4)
      ).map(([displayName, stableId]) => ({
        displayName,
        kind: "setup" as const,
        stableId,
        version: "1.0",
      })),
    ].map((item, index) => ({
      assignment_id: `assignment_${subject.id}_${index}`,
      display_name: item.displayName,
      object_kind: item.kind,
      organization_id: organization.organization_id,
      revision: 1,
      schema_version: 1,
      selector: "exact" as const,
      passport_digest: null,
      harness: null,
      source_team_id:
        subject.kind === "employee"
          ? (teamViews.find((candidate) =>
              candidate.members.some(
                (candidateMember) => candidateMember.account_id === subject.id,
              ),
            )?.team_id ?? null)
          : subject.kind === "team"
            ? subject.id
            : null,
      stable_id: item.stableId,
      state: "current",
      subject_id: subject.id,
      subject_kind: subject.kind === "employee" ? "employee" : subject.kind,
      version: item.version,
    }));
  });
}

function overviewResponse(): CorporateOverview {
  return {
    ...overviewGraph,
    nodes: overviewGraph.nodes.map((node) => ({
      ...node,
      assignments: catalogAssignments(node.kind, node.id),
      assignments_readable: true,
    })),
  };
}

export function corporateHandlers(
  method: string,
  path: string,
  auth: boolean,
  body: unknown,
  query = new URLSearchParams(),
  headers?: HeadersInit,
): WorkspaceMockResult | null {
  const [routePath, embeddedQuery] = path.split("?", 2);
  if (embeddedQuery) query = new URLSearchParams(embeddedQuery);
  path = routePath ?? path;
  const base = `/v1/corporate/organizations/${organization.organization_id}`;
  const capabilityPath = `/v1/organizations/${organization.organization_id}/capabilities`;
  if (path !== "/v1/organizations" && path !== capabilityPath && !path.startsWith("/v1/corporate/"))
    return null;
  if (!auth) return error(401, "AI_STP_UNAUTHORIZED");
  if (path === "/v1/organizations" && method === "GET")
    return ok(list([{ ...organization, kind: "corporate" }]));
  if (path === capabilityPath && method === "GET")
    return ok({ schema_version: 1, authorization_revision: "1", capabilities });
  const acceptMatch = path.match(/^\/v1\/corporate\/invitations\/([^/]+)\/accept$/);
  if (acceptMatch && method === "POST") {
    const invitation = mockInvitations.find(
      (item) => item.invitation_id === decodeURIComponent(acceptMatch[1] ?? ""),
    );
    const acceptBody = (body ?? {}) as { token?: unknown };
    if (!invitation || invitation.token !== acceptBody.token) return error(404, "AI_STP_NOT_FOUND");
    if (invitation.state !== "pending" || new Date(invitation.expires_at) < new Date())
      return error(409, "AI_STP_CONFLICT");
    invitation.state = "accepted";
    invitation.token = null;
    invitation.accepted_account_id = member.account_id;
    return ok(member);
  }
  if (!path.startsWith(`${base}/`)) return error(404, "AI_STP_NOT_FOUND");
  const suffix = path.slice(base.length + 1);
  if (suffix === "telemetry/heartbeat-report" && method === "GET") {
    const team = teamViews[0]!;
    const employee = team.members[0] ?? member;
    const teamOption = { id: team.team_id, name: team.name };
    const heartbeat = {
      account_id: employee.account_id,
      employee_name: employee.display_name ?? "Employee",
      teams: [teamOption],
      device_id: "device_01K6DASHBOARDMOCK00000000",
      device_name: "MacBook Pro",
      last_heartbeat_at: "2026-09-25T11:45:00Z",
      status: "active" as const,
      buckets: Array.from({ length: 60 }, (_, index) => ({
        start: new Date(Date.parse("2026-09-24T12:00:00Z") + index * 24 * 60_000).toISOString(),
        end: new Date(Date.parse("2026-09-24T12:00:00Z") + (index + 1) * 24 * 60_000).toISOString(),
        expected: 1,
        received: 1,
        state: "healthy" as const,
      })),
      coverage_percent: 100,
    };
    const matches =
      (!query.has("team") || query.getAll("team").includes(team.team_id)) &&
      (!query.has("employee") || query.getAll("employee").includes(employee.account_id)) &&
      (!query.has("status") || query.getAll("status").includes("active"));
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      evaluated_at: "2026-09-25T12:00:00Z",
      interval_seconds: 900,
      stale_after_seconds: 3600,
      total: matches ? 1 : 0,
      page: 1,
      page_size: 10,
      teams: [teamOption],
      employees: [
        { id: employee.account_id, name: heartbeat.employee_name, team_ids: [team.team_id] },
      ],
      items: matches ? [heartbeat] : [],
    });
  }
  if (suffix === "dashboard/views" && method === "GET")
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      items: dashboardViews,
    });
  if (suffix === "dashboard/views" && method === "POST") {
    const request = body as {
      name: string;
      scope: DashboardView["scope"];
      scope_id: string;
      query: DashboardQuery;
    };
    const view: DashboardView = {
      schema_version: 1,
      id: "dashboard_view_01K6DASHBOARDMOCK00000000",
      organization_id: organization.organization_id,
      owner_account_id: member.account_id,
      name: request.name,
      scope: request.scope,
      scope_id: request.scope_id,
      query: request.query,
      revision: 1,
    };
    dashboardViews.splice(0, dashboardViews.length, view);
    return ok(view);
  }
  if (suffix.startsWith("dashboard/views/") && method === "PUT") {
    const request = body as { name: string; query: DashboardQuery };
    const view = dashboardViews[0];
    if (!view) return error(404, "AI_STP_NOT_FOUND");
    const updated = {
      ...view,
      name: request.name,
      query: request.query,
      revision: view.revision + 1,
    };
    dashboardViews[0] = updated;
    return ok(updated);
  }
  if (suffix === "dashboard/query" && method === "POST") {
    const request = body as { query: DashboardQuery };
    const selected = [
      ...new Set([
        ...(request.query.dimensions ?? []),
        ...(request.query.group_by ?? []),
        ...(request.query.pivot_rows ?? []),
        ...(request.query.pivot_columns ?? []),
      ]),
    ];
    const source = {
      state: request.query.dataset === "ci" ? "fail" : "stale",
      project: projectViews[0]?.project_id ?? "",
      team: teamViews[0]?.team_id ?? "",
      account: member.account_id,
      device: "device_mock",
      harness: "codex",
      setup: "",
      provider: "mock-provider",
      day: "2026-09-22",
      checked_at: "2026-09-22T12:00:00Z",
      reason: "target_drift",
    };
    const matches = (request.query.filters ?? []).every((filter) =>
      filter.values.includes(source[filter.dimension]),
    );
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      query: request.query,
      evaluated_at: "2026-09-22T12:00:00Z",
      total_source_rows: matches ? 1 : 0,
      total_groups: matches ? 1 : 0,
      items: matches
        ? [
            {
              dimensions: Object.fromEntries(selected.map((key) => [key, source[key]])),
              measures: Object.fromEntries(
                (request.query.measures ?? ["count"]).map((key) => [key, 1]),
              ),
            },
          ]
        : [],
    });
  }
  const target = resourceEntries()
    .flatMap(([, items]) => items)
    .find((item) => suffix === `entity-profiles/${item.kind}/${item.id}`);
  if (target) return corporateProfileHandler(method, suffix, body, target);
  const mediaTarget = resourceEntries()
    .flatMap(([, items]) => items)
    .find((item) => suffix === `profiles/${item.kind}/${item.id}/media`);
  if (mediaTarget) return corporateMediaUploadHandler(method, body, query, headers, mediaTarget);
  const areaWriteMatch = suffix.match(/^technology-areas(?:\/([^/]+)(?:\/lifecycle)?)?$/);
  if (areaWriteMatch && method !== "GET") {
    const areaId = areaWriteMatch[1];
    if (!areaId && method === "POST") {
      const write = body as { metadata?: { name?: string; description?: string }; state?: string };
      const area: AreaView = {
        area_id: `area_${String(areaViews.length + 1).padStart(26, "0")}`,
        organization_id: organization.organization_id,
        name: write.metadata?.name ?? "",
        description: write.metadata?.description ?? "",
        provenance: "offline-fixture",
        revision: 1,
        state: (write.state === "draft" ? "draft" : "active") as "draft" | "active",
      };
      areaViews.push(area);
      return ok(area);
    }
    const area = areaViews.find((item) => item.area_id === areaId);
    if (!area) return error(404, "AI_STP_NOT_FOUND");
    if (suffix.endsWith("/lifecycle") && method === "POST") {
      const write = body as { target?: "draft" | "active" | "archived" };
      if (write.target) area.state = write.target;
      area.revision += 1;
      return ok(area);
    }
    if (method === "PUT") {
      const write = body as { metadata?: { name?: string; description?: string } };
      if (write.metadata?.name !== undefined) area.name = write.metadata.name;
      if (write.metadata?.description !== undefined) area.description = write.metadata.description;
      area.revision += 1;
      return ok(area);
    }
    if (method === "DELETE") {
      area.state = "archived";
      area.revision += 1;
      return ok(area);
    }
    return error(405, "AI_STP_VALIDATION_ERROR");
  }
  if (suffix === "technology-scans" && method === "POST") {
    const launch = body as { project_ids?: string[] };
    const items = (launch.project_ids ?? []).map((projectId) => {
      const project = projectViews.find((item) => item.project_id === projectId);
      const linked = Boolean(project?.repositories?.[0]?.repository_url);
      const scanId = `scan_${String(mockScanEntries.length + 1).padStart(24, "0")}`;
      if (linked) {
        mockScanEntries.push({
          scan_id: scanId,
          project_id: projectId,
          project_name: project?.name ?? projectId,
          repository: project?.repositories?.[0]?.repository_url ?? null,
          source: "github",
          branch: project?.repositories?.[0]?.default_branch ?? null,
          commit: null,
          created_at: new Date().toISOString(),
          status: "queued",
          found: 0,
          pending: 0,
        });
      }
      return {
        project_id: projectId,
        scan_id: linked ? scanId : null,
        job_id: linked ? mockScanEntries.length : null,
        state: (linked ? "queued" : "rejected") as "queued" | "rejected",
        detail: linked ? null : "no_linked_repository",
      };
    });
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      items,
    });
  }
  if (suffix === "technology-unmapped-coordinates" && method === "PATCH") {
    const patch = body as {
      kind?: string;
      coordinate?: string;
      candidate_technology_id?: string | null;
    };
    const row = unmappedCoordinates.find(
      (item) => item.kind === patch.kind && item.coordinate === patch.coordinate,
    );
    if (!row) return error(404, "AI_STP_NOT_FOUND");
    row.candidate_technology_id = patch.candidate_technology_id ?? null;
    return ok(row);
  }
  const mappingMatch = suffix.match(/^technology-mappings\/([^/]+)$/);
  if (mappingMatch && method === "PUT") {
    const version = decodeURIComponent(mappingMatch[1] ?? "");
    const write = body as { entries?: TechnologyMappingEntry[] };
    const entries = write.entries ?? [];
    const snapshot: TechnologyMappingView = {
      digest: `sha256:${version}`,
      entries,
      organization_id: organization.organization_id,
      version,
    };
    mappingSnapshots.push(snapshot);
    for (const row of unmappedCoordinates) {
      const applied = entries.find(
        (item) => item.kind === row.kind && item.coordinate === row.coordinate,
      );
      if (applied) {
        row.state = "resolved";
        row.resolved_technology_id = applied.technology_id;
        row.candidate_technology_id = null;
      }
    }
    return ok(snapshot);
  }
  if (suffix === "invitations") {
    if (method === "GET") return ok({ schema_version: 1, items: mockInvitations });
    if (method === "POST") {
      const payload = (body ?? {}) as Record<string, unknown>;
      const text = (key: string, fallback = "") =>
        typeof payload[key] === "string" ? (payload[key] as string) : fallback;
      const invitation: CorporateInvitation = {
        schema_version: 1,
        invitation_id: `invitation_${String(mockInvitations.length + 1).padStart(4, "0")}`,
        organization_id: organization.organization_id,
        recipient_email: text("recipient_email"),
        issuer_account_id: employeeNodes[0]?.id ?? null,
        display_name: text("display_name"),
        role: text("role", "staff"),
        team_ids: Array.isArray(payload.team_ids) ? (payload.team_ids as string[]) : [],
        project_ids: [],
        job_title_id: null,
        accepted_account_id: null,
        claimant_account_id: null,
        state: "pending",
        delivery_state: "sent",
        delivery_error: null,
        created_at: new Date().toISOString(),
        expires_at: new Date(
          Date.now() + Number(payload.ttl_seconds ?? 86_400) * 1000,
        ).toISOString(),
        token: `tok_${Math.random().toString(36).slice(2, 18)}`,
      };
      mockInvitations.push(invitation);
      return ok(invitation);
    }
  }
  const revokeMatch = suffix.match(/^invitations\/([^/]+)\/revoke$/);
  if (revokeMatch && method === "POST") {
    const invitation = mockInvitations.find((item) => item.invitation_id === revokeMatch[1]);
    if (!invitation) return error(404, "AI_STP_NOT_FOUND");
    invitation.state = "revoked";
    invitation.token = null;
    return ok(invitation);
  }
  if (suffix === "membership/policy") {
    if (method === "PUT") {
      const payload = (body ?? {}) as { allowed_email_domains?: string[] };
      mockPolicy.allowed_email_domains = payload.allowed_email_domains ?? [];
      mockPolicy.authorization_revision += 1;
    }
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      ...mockPolicy,
    });
  }
  const textField = (key: string, fallback = "") => {
    const value = ((body ?? {}) as Record<string, unknown>)[key];
    return typeof value === "string" ? value.trim() : fallback;
  };
  if (suffix === "roles" && method === "POST") {
    const name = textField("name");
    const parent = textField("parent_role") || null;
    if (!name || builtInRoles.has(name) || mockRoles.some((item) => item.name === name))
      return error(409, "AI_STP_CONFLICT");
    if (parent && !mockRoles.some((item) => item.name === parent))
      return error(422, "AI_STP_VALIDATION_ERROR");
    const permissions = ((body ?? {}) as Record<string, unknown>).permissions;
    const role: CorporateRoleView = {
      schema_version: 1,
      name,
      parent_role: parent,
      permissions: Array.isArray(permissions)
        ? permissions.filter((item): item is string => typeof item === "string")
        : [],
      revision: 1,
    };
    mockRoles.push(role);
    return ok(role);
  }
  const roleMatch = suffix.match(/^roles\/([^/]+)$/);
  if (roleMatch && method !== "GET") {
    const name = decodeURIComponent(roleMatch[1] ?? "");
    const role = mockRoles.find((item) => item.name === name);
    if (!role) return error(404, "AI_STP_NOT_FOUND");
    if (builtInRoles.has(role.name)) return error(403, "AI_STP_FORBIDDEN");
    if (method === "DELETE") {
      mockRoles.splice(mockRoles.indexOf(role), 1);
      return ok({ schema_version: 1, resource_id: name });
    }
    if (method === "PATCH") {
      const parent = textField("parent_role");
      role.parent_role = parent || null;
      const permissions = ((body ?? {}) as Record<string, unknown>).permissions;
      if (Array.isArray(permissions))
        role.permissions = permissions.filter((item): item is string => typeof item === "string");
      role.revision += 1;
      return ok(role);
    }
  }
  if (suffix === "bindings" && method === "POST") {
    const role = textField("role");
    const accountId = textField("account_id");
    if (!role || !accountId) return error(422, "AI_STP_VALIDATION_ERROR");
    const binding: CorporateBinding = {
      schema_version: 1,
      binding_id: `binding_${crypto.randomUUID().replaceAll("-", "").slice(0, 21)}`,
      account_id: accountId,
      service_principal_id: null,
      principal_type: "user",
      role,
      scope_kind: (textField("scope_kind", "organization") || "organization") as never,
      scope_id: textField("scope_id") || organization.organization_id,
      state: "active",
      revision: 1,
      origin: "direct",
      coverage: textField("coverage") === "descendants" ? "descendants" : "self",
    };
    mockBindings.push(binding);
    return ok(binding);
  }
  const bindingMatch = suffix.match(/^bindings\/([^/]+)$/);
  if (bindingMatch && method !== "GET") {
    const binding = mockBindings.find((item) => item.binding_id === bindingMatch[1]);
    if (!binding) return error(404, "AI_STP_NOT_FOUND");
    if (method === "DELETE") {
      binding.state = "revoked";
      return ok({ schema_version: 1, resource_id: binding.binding_id });
    }
    if (method === "PATCH") {
      binding.state = textField("state", "active") === "revoked" ? "revoked" : "active";
      binding.revision += 1;
      return ok(binding);
    }
  }
  if (suffix === "permission-grants") {
    if (method === "POST") {
      const permission = textField("permission");
      if (!permission) return error(422, "AI_STP_VALIDATION_ERROR");
      const grant: CorporatePermissionGrant = {
        schema_version: 1,
        grant_id: `grant_${crypto.randomUUID().replaceAll("-", "").slice(0, 21)}`,
        account_id: textField("account_id") || null,
        service_principal_id: textField("service_principal_id") || null,
        principal_type: "user",
        permission,
        scope_kind: (textField("scope_kind", "organization") || "organization") as never,
        scope_id: textField("scope_id") || organization.organization_id,
        state: "active",
        issuer_account_id: member.account_id,
        revision: 1,
      };
      mockGrants.push(grant);
      return ok(grant);
    }
  }
  const grantMatch = suffix.match(/^permission-grants\/([^/]+)$/);
  if (grantMatch && method === "DELETE") {
    const grant = mockGrants.find((item) => item.grant_id === grantMatch[1]);
    if (!grant) return error(404, "AI_STP_NOT_FOUND");
    grant.state = "revoked";
    grant.revision += 1;
    return ok(grant);
  }
  if (suffix === "service-principals" && method === "POST") {
    const name = textField("name");
    if (!name) return error(422, "AI_STP_VALIDATION_ERROR");
    const principal: CorporateServicePrincipalView = {
      schema_version: 1,
      service_principal_id: `service_principal_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`,
      organization_id: organization.organization_id,
      name,
      state: "active",
      revision: 1,
      binding: {
        schema_version: 1,
        binding_id: `binding_${crypto.randomUUID().replaceAll("-", "").slice(0, 21)}`,
        account_id: null,
        service_principal_id: null,
        principal_type: "service_principal",
        role: textField("role", "staff") || "staff",
        scope_kind: (textField("scope_kind", "organization") || "organization") as never,
        scope_id: textField("scope_id") || organization.organization_id,
        state: "active",
        revision: 1,
        origin: "service_principal",
        coverage: "self",
      },
    };
    principal.binding.service_principal_id = principal.service_principal_id;
    mockServicePrincipals.push(principal);
    return ok(principal);
  }
  const principalMatch = suffix.match(/^service-principals\/([^/]+)$/);
  if (principalMatch && method !== "GET") {
    const principal = mockServicePrincipals.find(
      (item) => item.service_principal_id === principalMatch[1],
    );
    if (!principal) return error(404, "AI_STP_NOT_FOUND");
    if (method === "DELETE") {
      mockServicePrincipals.splice(mockServicePrincipals.indexOf(principal), 1);
      return ok({ schema_version: 1, resource_id: principal.service_principal_id });
    }
    if (method === "PATCH") {
      principal.state = textField("state") === "suspended" ? "suspended" : "active";
      principal.revision += 1;
      return ok(principal);
    }
  }
  if (suffix === "members" && method === "POST") {
    const accountId = `account_${crypto.randomUUID().replaceAll("-", "").slice(0, 26)}`;
    const created: CorporateMember = {
      schema_version: 1,
      account_id: accountId,
      display_name: textField("display_name") || null,
      state: "active",
      role: textField("role", "staff") || "staff",
      job_title_id: null,
      job_title_name: null,
      contact_email: textField("email") || null,
      joined_at: new Date().toISOString(),
      last_activity_at: null,
      revision: 1,
      available_actions: [],
    };
    members.push(created);
    memberById.set(accountId, created);
    resources.members.push({
      id: accountId,
      name: created.display_name ?? accountId,
      kind: "employee",
      detail: created,
    });
    return ok(created);
  }
  const memberMutationMatch = suffix.match(/^members\/([^/]+)$/);
  if (memberMutationMatch && method === "PATCH") {
    const target = memberById.get(decodeURIComponent(memberMutationMatch[1] ?? ""));
    if (!target) return error(404, "AI_STP_NOT_FOUND");
    const role = textField("role");
    const state = textField("state");
    if (role) target.role = role;
    if (state === "suspended" || state === "active") target.state = state;
    target.revision += 1;
    return ok(target);
  }
  if (memberMutationMatch && method === "DELETE") {
    const accountId = decodeURIComponent(memberMutationMatch[1] ?? "");
    const target = memberById.get(accountId);
    if (!target) return error(404, "AI_STP_NOT_FOUND");
    const index = members.indexOf(target);
    if (index >= 0) members.splice(index, 1);
    memberById.delete(accountId);
    resources.members = resources.members.filter((item) => item.id !== accountId);
    return ok({ schema_version: 1, resource_id: accountId });
  }
  if (suffix === "membership-assignments" && method === "POST") {
    const accountId = textField("account_id");
    const target = memberById.get(accountId);
    if (!target) return error(404, "AI_STP_NOT_FOUND");
    const teamId = textField("team_id");
    if (teamId) {
      const team = teamViews.find((item) => item.team_id === teamId);
      const operation = textField("operation", "assign") || "assign";
      if (team) {
        const already = team.members.some((item) => item.account_id === accountId);
        if (operation === "assign" && !already) team.members.push(target);
        if (operation === "remove")
          team.members = team.members.filter((item) => item.account_id !== accountId);
      }
    }
    return ok({ schema_version: 1, member: target });
  }
  if (method !== "GET") return error(405, "AI_STP_VALIDATION_ERROR");
  if (suffix === "technology-unmapped-coordinates")
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      coordinates: unmappedCoordinates,
    });
  if (suffix === "technology-mappings")
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      items: mappingSnapshots.map((snapshot) => ({
        version: snapshot.version,
        digest: snapshot.digest,
        entries: snapshot.entries.length,
      })),
    });
  if (mappingMatch) {
    const version = decodeURIComponent(mappingMatch[1] ?? "");
    const snapshot = mappingSnapshots.find((item) => item.version === version);
    return snapshot ? ok(snapshot) : error(404, "AI_STP_NOT_FOUND");
  }
  if (suffix === "context") return ok(context);
  if (suffix === "overview") return ok(overviewResponse());
  if (suffix === "directory") return corporateDirectoryResponse(query);
  if (suffix === "roles") return ok({ schema_version: 1, items: mockRoles });
  if (suffix === "catalog-assignments")
    return ok({
      schema_version: 1,
      items: catalogAssignments(
        query.get("subject_kind") ?? undefined,
        query.get("subject_id") ?? undefined,
      ),
      total: catalogAssignments(
        query.get("subject_kind") ?? undefined,
        query.get("subject_id") ?? undefined,
      ).length,
    });
  if (suffix === "catalog-usage") return ok({ schema_version: 1, items: [], total: 0 });
  if (suffix === "bindings") return ok({ schema_version: 1, items: mockBindings });
  if (suffix === "service-principals")
    return ok({ schema_version: 1, items: mockServicePrincipals });
  if (suffix === "permission-grants") {
    const accountId = query.get("account_id");
    return ok({
      schema_version: 1,
      items: accountId ? mockGrants.filter((item) => item.account_id === accountId) : mockGrants,
    });
  }
  if (suffix === "delegation")
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      authorization_revision: 1,
      descendants_coverage: true,
      grantable_roles: mockRoles.map((item) => ({
        name: item.name,
        permissions: item.permissions,
      })),
    } satisfies CorporateDelegationView);
  const accessMatch = suffix.match(/^members\/([^/]+)\/access$/);
  if (accessMatch) {
    const accountId = decodeURIComponent(accessMatch[1] ?? "");
    const target = memberById.get(accountId);
    if (!target) return error(404, "AI_STP_NOT_FOUND");
    const bindings = mockBindings.filter((item) => item.account_id === accountId);
    const grants = mockGrants.filter((item) => item.account_id === accountId);
    const scopeKind = query.get("scope_kind") ?? "organization";
    const scopeId =
      query.get("scope_id") ??
      (scopeKind === "organization" ? organization.organization_id : (teamViews[0]?.team_id ?? ""));
    const effective: CorporateEffectivePermission[] = bindings.flatMap((binding) =>
      (mockRoles.find((item) => item.name === binding.role)?.permissions ?? []).map(
        (permission) => ({
          permission,
          scope_kind: scopeKind as never,
          scope_id: scopeId,
          sources: ["binding", "membership"],
          source_records: [
            {
              kind: "binding",
              source_id: binding.binding_id,
              role: binding.role,
              scope_kind: binding.scope_kind,
              scope_id: binding.scope_id,
              origin: binding.origin,
            },
          ],
        }),
      ),
    );
    const privateGrants: CorporateMemberPrivateGrant[] = grants.map((grant) => ({
      schema_version: 1,
      grant_id: grant.grant_id,
      issuer_account_id: grant.issuer_account_id,
      object_kind: "component",
      stable_id: grant.scope_id,
      major: 1,
      state: grant.state === "active" ? "active" : "revoked",
    }));
    return ok({
      schema_version: 1,
      account_id: accountId,
      organization_id: organization.organization_id,
      scope_kind: scopeKind as never,
      scope_id: scopeId,
      authorization_revision: 1,
      bindings,
      grants,
      private_grants: privateGrants,
      effective,
    } satisfies CorporateMemberAccess);
  }
  if (suffix === "permissions/matrix") {
    const scopeMap: Record<string, CorporatePermissionDefinition["scopes"]> = {
      member: ["organization", "member"],
      project: ["organization", "project"],
      team: ["organization", "team"],
      technology: ["organization", "technology"],
      catalog_object: ["organization", "catalog_object"],
      telemetry: ["organization", "member"],
    };
    const definitions = capabilities.map((permission) => {
      const [resource, action] = permission.split(".", 2);
      return {
        name: permission,
        resource: resource ?? permission,
        action: action ?? "",
        group: resource ?? permission,
        scopes: scopeMap[resource ?? ""] ?? ["organization"],
        create_parent: action === "create" || action === "invite" ? "organization" : null,
        implementation: "enforced",
      } satisfies CorporatePermissionDefinition;
    });
    const effective: CorporateEffectivePermission[] = capabilities.map((permission) => ({
      permission,
      scope_kind: "organization",
      scope_id: organization.organization_id,
      sources: ["binding"],
      source_records: [
        {
          kind: "binding",
          source_id: mockBindings[0]?.binding_id ?? "binding_0",
          role: "superadmin",
          scope_kind: "organization",
          scope_id: organization.organization_id,
          origin: "membership",
        },
      ],
    }));
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      authorization_revision: 1,
      definitions,
      effective,
    } satisfies CorporatePermissionMatrix);
  }
  if (suffix === "job-titles") return ok({ schema_version: 1, items: [] });
  if (suffix === "audit") return ok({ schema_version: 1, items: [] });
  if (suffix === "technology-areas") return ok({ schema_version: 1, items: areaViews });
  const areaMatch = suffix.match(/^technology-areas\/([^/]+)$/);
  if (areaMatch) {
    const area = areaViews.find((item) => item.area_id === areaMatch[1]);
    return area ? ok(area) : error(404, "AI_STP_NOT_FOUND");
  }
  if (suffix === "technology-scans") {
    const projectId = query.get("project_id");
    const items = projectId
      ? mockScanEntries.filter((item) => item.project_id === projectId)
      : mockScanEntries;
    return ok({
      schema_version: 1,
      organization_id: organization.organization_id,
      items,
      total: items.length,
    });
  }
  const scanMatch = suffix.match(/^technology-scans\/([^/]+)$/);
  if (scanMatch) {
    const scan = mockScanEntries.find((item) => item.scan_id === scanMatch[1]);
    if (!scan) return error(404, "AI_STP_NOT_FOUND");
    return ok({
      ...scan,
      complete: scan.status === "succeeded" || scan.status === "failed",
      detector_version: "2",
      mapping_version: null,
      findings: [],
    });
  }
  if (suffix === "technology-categories") return ok({ schema_version: 1, items: categoryViews });
  const categoryMatch = suffix.match(/^technology-categories\/([^/]+)$/);
  if (categoryMatch) {
    const category = categoryViews.find((item) => item.category_id === categoryMatch[1]);
    return category ? ok(category) : error(404, "AI_STP_NOT_FOUND");
  }
  for (const [resource, items] of resourceEntries()) {
    if (suffix === resource)
      return ok({ schema_version: 1, items: items.map((item) => item.detail) });
    const itemMatch = suffix.match(new RegExp(`^${resource}/([^/]+)$`));
    if (itemMatch) {
      const item = items.find((candidate) => candidate.id === itemMatch[1]);
      return item ? ok(item.detail) : error(404, "AI_STP_NOT_FOUND");
    }
  }
  const projectTeamsMatch = suffix.match(/^projects\/([^/]+)\/teams$/);
  if (projectTeamsMatch)
    return ok(
      list(projectTeamRelations.filter((item) => item.project_id === projectTeamsMatch[1])),
    );
  const teamProjectsMatch = suffix.match(/^teams\/([^/]+)\/projects$/);
  if (teamProjectsMatch)
    return ok(list(projectTeamRelations.filter((item) => item.team_id === teamProjectsMatch[1])));
  const projectTechMatch = suffix.match(/^projects\/([^/]+)\/technologies$/);
  if (projectTechMatch)
    return ok(
      list(projectTechnologyRelations.filter((item) => item.project_id === projectTechMatch[1])),
    );
  const techProjectsMatch = suffix.match(/^technologies\/([^/]+)\/projects$/);
  if (techProjectsMatch)
    return ok(
      list(
        projectTechnologyRelations.filter((item) => item.technology_id === techProjectsMatch[1]),
      ),
    );
  const techTeamsMatch = suffix.match(/^technologies\/([^/]+)\/responsible-teams$/);
  if (techTeamsMatch) {
    const technologyId = techTeamsMatch[1] ?? "";
    const relationTeamIds =
      technologyTeams.get(technologyId) ??
      (technologyId === technologies[0]?.technology_id ? [teamViews[0]?.team_id ?? ""] : []);
    const relations = relationTeamIds.filter(Boolean).map((teamId) => ({
      team_id: teamId,
      technology_id: technologyId,
      organization_id: organization.organization_id,
      relation_id: `${technologyId}:team:${teamId}`,
      revision: 1,
      state: "current",
    }));
    return ok({ schema_version: 1, items: relations, total: relations.length });
  }
  const techEmployeesMatch = suffix.match(/^technologies\/([^/]+)\/employees$/);
  if (techEmployeesMatch)
    return ok({
      schema_version: 1,
      items: employeeTechnologyRelations.filter(
        (item) => item.technology_id === techEmployeesMatch[1],
      ),
      total: employeeTechnologyRelations.filter(
        (item) => item.technology_id === techEmployeesMatch[1],
      ).length,
    });
  const memberProjectsMatch = suffix.match(/^members\/([^/]+)\/projects$/);
  if (memberProjectsMatch) {
    const teamIds = teamViews
      .filter((candidate) =>
        candidate.members.some((item) => item.account_id === memberProjectsMatch[1]),
      )
      .map((candidate) => candidate.team_id);
    const projectIds = projectTeamRelations
      .filter((item) => teamIds.includes(item.team_id))
      .map((item) => item.project_id);
    return ok(list(projectViews.filter((item) => projectIds.includes(item.project_id))));
  }
  const projectMembersMatch = suffix.match(/^projects\/([^/]+)\/members$/);
  if (projectMembersMatch) {
    const teamIds = projectTeamRelations
      .filter((item) => item.project_id === projectMembersMatch[1])
      .map((item) => item.team_id);
    return ok(
      list(
        teamViews.filter((item) => teamIds.includes(item.team_id)).flatMap((item) => item.members),
      ),
    );
  }
  const memberTechMatch = suffix.match(/^members\/([^/]+)\/technologies$/);
  if (memberTechMatch)
    return ok({
      schema_version: 1,
      items: employeeTechnologyRelations.filter((item) => item.account_id === memberTechMatch[1]),
      total: employeeTechnologyRelations.filter((item) => item.account_id === memberTechMatch[1])
        .length,
    });
  return error(404, "AI_STP_NOT_FOUND");
}
