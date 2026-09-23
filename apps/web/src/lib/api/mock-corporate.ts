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
  CorporateOverview,
  CorporateContext,
  CorporateTeamView,
  CorporateProjectView,
  CorporateMember,
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
const projectViews: CorporateProjectView[] = projectNodes.map((item) => ({
  schema_version: 1,
  project_id: item.id,
  organization_id: organization.organization_id,
  name: item.name,
  state: "active",
  lifecycle: "active",
  revision: 1,
  repository_activity_at: null,
  source_availability: "unknown",
  repositories: [],
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
const technologyById = new Map(technologies.map((item) => [item.technology_id, item]));
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
  "project.list",
  "project.read",
  "member.read",
  "member.manage",
  "member.list",
  "role.list",
  "binding.list",
  "audit.list",
  "technology.list",
  "technology.read",
  "project_team.list",
  "project_team.read",
  "project_technology.list",
  "project_technology.read",
  "technology_team.list",
  "technology_team.read",
  "category.list",
  "category.read",
  "technology_decision.read",
];
const context: CorporateContext = {
  schema_version: 1,
  organization,
  member,
  teams: teamViews,
  projects: projectViews,
  bindings: [],
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
  if (!path.startsWith(`${base}/`)) return error(404, "AI_STP_NOT_FOUND");
  const suffix = path.slice(base.length + 1);
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
  if (method !== "GET") return error(405, "AI_STP_VALIDATION_ERROR");
  if (suffix === "context") return ok(context);
  if (suffix === "overview") return ok(overviewResponse());
  if (suffix === "directory") return corporateDirectoryResponse(query);
  if (suffix === "roles")
    return ok({
      schema_version: 1,
      items: [...new Set(roles)].map((name) => ({
        schema_version: 1,
        name,
        parent_role: null,
        permissions: [],
        revision: 1,
      })),
    });
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
