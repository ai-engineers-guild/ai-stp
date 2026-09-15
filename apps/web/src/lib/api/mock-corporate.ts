/** Offline fixtures only. Dispatch exclusively from the existing mock transport. */
import { z } from "zod";
import fixture from "../../../../../packages/contracts/src/ai_stp_contracts/fixtures/v1/corporate-overview.json";
import { errorBody } from "@/mocks/fixtures";
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
} from "./generated/types.gen";
import type { WorkspaceMockResult } from "./mock-workspace";

const graph = fixture.cases[0]?.body as CorporateOverview;
const organization = graph.organization;
const node = (kind: string) => {
  const result = graph.nodes.find((item) => item.kind === kind);
  if (!result) throw new Error(`Missing corporate fixture node: ${kind}`);
  return result;
};
const employee = node("employee");
const teamNode = node("team");
const projectNode = node("project");
const member: CorporateMember = {
  schema_version: 1,
  account_id: employee.id,
  display_name: employee.name,
  state: "active",
  role: "team_lead",
  revision: 1,
};
const team: CorporateTeamView = {
  schema_version: 1,
  team_id: teamNode.id,
  organization_id: organization.organization_id,
  name: teamNode.name,
  description: "Offline **team** fixture",
  state: "active",
  revision: 1,
  lead_account_ids: [member.account_id],
  members: [member],
};
const project: CorporateProjectView = {
  schema_version: 1,
  project_id: projectNode.id,
  organization_id: organization.organization_id,
  name: projectNode.name,
  state: "active",
  lifecycle: "active",
  revision: 1,
};
const technology: TechnologyView = {
  schema_version: 1,
  technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  organization_id: organization.organization_id,
  name: "Offline technology",
  description: "Offline **technology** fixture",
  aliases: [],
  category_ids: [],
  official_urls: [],
  icon_url: null,
  lifecycle: "active",
  restore_lifecycle: "active",
  redirect_id: null,
  revision: 1,
  provenance: "manual",
};
const projectTeamRelation = {
  organization_id: organization.organization_id,
  project_id: project.project_id,
  relation_id: `${project.project_id}:team:${team.team_id}`,
  revision: 1,
  role: "owner",
  state: "current",
  team_id: team.team_id,
} satisfies ProjectTeamView;
const projectTechnologyRelation = {
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
  project_id: project.project_id,
  relation_id: `${project.project_id}:technology:${technology.technology_id}`,
  revision: 1,
  state: "current",
  technology_id: technology.technology_id,
} satisfies ProjectTechnologyView;
const relationResponses: Record<string, unknown[]> = {
  [`projects/${project.project_id}/teams`]: [projectTeamRelation],
  [`teams/${team.team_id}/projects`]: [projectTeamRelation],
  [`projects/${project.project_id}/technologies`]: [projectTechnologyRelation],
  [`technologies/${technology.technology_id}/projects`]: [projectTechnologyRelation],
};
// This fixture projection is not evidence of production RBAC enforcement.
const capabilities = [
  "team.list",
  "project.list",
  "project.read",
  "member.list",
  "technology.list",
  "technology.read",
  "project_team.list",
  "project_team.read",
  "project_technology.list",
  "project_technology.read",
];
const context: CorporateContext = {
  schema_version: 1,
  organization,
  member,
  teams: [team],
  projects: [project],
  bindings: [],
  capabilities,
};
const resources = {
  teams: { id: team.team_id, name: team.name, kind: "team", detail: team },
  projects: { id: project.project_id, name: project.name, kind: "project", detail: project },
  members: { id: member.account_id, name: employee.name, kind: "employee", detail: member },
  technologies: {
    id: technology.technology_id,
    name: technology.name,
    kind: "technology",
    detail: technology,
  },
};
type CorporateResource = (typeof resources)[keyof typeof resources];
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

function initialProfile(item: CorporateResource): Profile {
  return {
    name: item.name,
    revision: 0,
    can_edit: true,
    avatar_url: null,
    owner_account_id: item.kind === "technology" ? member.account_id : null,
    fields: {
      description: `Offline **${item.kind}** fixture`,
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
    avatar_url: assetId ? (uploads.get(assetId)?.receipt.public_url ?? null) : null,
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
  if (method === "GET") return ok(hydrateProfileAvatar(current));
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
      fields: effect.fields,
      revision: current.revision + 1,
    }),
  );
  profiles.set(suffix, result);
  receipts.set(receiptKey, { effect: fingerprint, result });
  return ok(result);
}

function corporateDirectoryResponse(query: URLSearchParams): WorkspaceMockResult {
  const resource = query.get("resource");
  const item = Object.entries(resources).find(([key]) => key === resource)?.[1];
  if (!item) return error(422, "AI_STP_VALIDATION_ERROR");
  const ref = (id: string, name: string) => ({ id, name });
  const card = {
    id: item.id,
    name: item.name,
    state: "active",
    leads: [ref(member.account_id, employee.name)],
    teams: [ref(team.team_id, team.name)],
    projects: [ref(project.project_id, project.name)],
    technologies: [ref(technology.technology_id, technology.name)],
    owner_team: ref(team.team_id, team.name),
    owner: ref(member.account_id, employee.name),
    is_lead: resource === "members",
  };
  const items = Number(query.get("offset") ?? 0) === 0 ? [card] : [];
  return ok({
    ...list(items),
    total: 1,
    organization,
    resource,
    facets: {
      leads: card.leads,
      teams: card.teams,
      technologies: card.technologies,
      projects: card.projects,
      categories: [],
    },
  });
}

export function corporateHandlers(
  method: string,
  path: string,
  auth: boolean,
  body: unknown,
  query = new URLSearchParams(),
  headers?: HeadersInit,
): WorkspaceMockResult | null {
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
  const target = Object.entries(resources).find(
    ([, item]) => suffix === `entity-profiles/${item.kind}/${item.id}`,
  );
  if (target) return corporateProfileHandler(method, suffix, body, target[1]);
  const mediaTarget = Object.entries(resources).find(
    ([, item]) => suffix === `profiles/${item.kind}/${item.id}/media`,
  );
  if (mediaTarget) return corporateMediaUploadHandler(method, body, query, headers, mediaTarget[1]);
  if (method !== "GET") return error(405, "AI_STP_VALIDATION_ERROR");
  if (suffix === "context") return ok(context);
  if (suffix === "overview") return ok(graph);
  if (suffix === "directory") return corporateDirectoryResponse(query);
  const relationItems = relationResponses[suffix];
  if (relationItems) return ok(list(relationItems));
  for (const [resource, item] of Object.entries(resources)) {
    if (suffix === resource) return ok(list([item.detail]));
    if (suffix === `${resource}/${item.id}`) return ok(item.detail);
  }
  if (suffix === "catalog-assignments") return ok(list([]));
  if (suffix === `members/${member.account_id}/projects`) return ok(list([project]));
  if (suffix === `projects/${project.project_id}/members`) return ok(list([member]));
  if (suffix === `members/${member.account_id}/technologies`) return ok(list([]));
  return error(404, "AI_STP_NOT_FOUND");
}
