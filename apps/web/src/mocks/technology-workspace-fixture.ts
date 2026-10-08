/** Explicit Storybook/component-test data; never used by the live API. */
import type {
  AreaView,
  CategoryView,
  CorporateProjectView,
  TechnologyLandscapeView,
  TechnologyScanDetail,
  TechnologyView,
} from "@/lib/api/generated/types.gen";
export const organizationId = "organization_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
export const authority = {
  organizationId,
  authorizationRevision: 1,
  csrfToken: "storybook-fixture",
};
export const areas: [AreaView] = [
  {
    schema_version: 1,
    organization_id: organizationId,
    area_id: "area_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    name: "Server applications",
    description: "",
    revision: 1,
    provenance: "storybook",
    state: "active",
  },
];
export const categories: [CategoryView] = [
  {
    schema_version: 1,
    organization_id: organizationId,
    category_id: "category_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    area_id: areas[0].area_id,
    name: "API frameworks",
    description: "",
    revision: 1,
    provenance: "storybook",
    state: "active",
  },
];
export const technologies: [TechnologyView] = [
  {
    schema_version: 1,
    organization_id: organizationId,
    technology_id: "technology_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    name: "FastAPI",
    description: "Python API framework",
    aliases: ["fastapi"],
    category_ids: [categories[0].category_id],
    icon_url: null,
    official_urls: [],
    lifecycle: "active",
    restore_lifecycle: "draft",
    revision: 1,
    redirect_id: null,
    owner_account_id: null,
    provenance: "storybook",
    available_actions: [],
  },
];
export const projects: [CorporateProjectView] = [
  {
    schema_version: 1,
    organization_id: organizationId,
    project_id: "remote_project_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    name: "Platform API",
    description: "",
    revision: 1,
    state: "active",
    repositories: [],
    available_actions: [],
    lifecycle: "active",
    source_availability: "available",
  },
];
export const scan: TechnologyScanDetail & {
  findings: [TechnologyScanDetail["findings"][number], TechnologyScanDetail["findings"][number]];
  repository: string;
} = {
  scan_id: "scan_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  project_id: projects[0].project_id,
  project_name: projects[0].name,
  repository: "https://gitlab.example/platform/api",
  source: "gitlab",
  branch: "main",
  commit: "a7b1c9e123456789",
  created_at: "2026-10-08T10:00:00Z",
  status: "succeeded",
  found: 2,
  pending: 1,
  duration_seconds: 312,
  error: null,
  scope: "dependencies",
  scan_types: ["dependencies"],
  detector_version: "repository-content-v1",
  mapping_version: "storybook-v1",
  complete: true,
  findings: [
    {
      kind: "package",
      coordinate: "fastapi",
      context: "production",
      version: "0.115",
      version_kind: "declared_range",
      state: "resolved",
      technology_id: technologies[0].technology_id,
      candidate_technology_id: null,
      review: "confirmed",
      review_revision: 1,
      comment: "",
      evidence: [
        {
          source: "declared",
          path: "requirements.txt",
          reference: "fastapi==0.115",
          observed_at: "2026-10-08T10:00:00Z",
          detector_version: "repository-content-v1",
          mapping_version: "storybook-v1",
        },
      ],
    },
    {
      kind: "package",
      coordinate: "weirdlib",
      context: "production",
      version: "^2.0",
      version_kind: "declared_range",
      state: "open",
      technology_id: null,
      candidate_technology_id: null,
      review: "proposed",
      review_revision: 0,
      comment: "",
      evidence: [
        {
          source: "declared",
          path: "package.json",
          reference: "dependencies.weirdlib",
          observed_at: "2026-10-08T10:00:00Z",
          detector_version: "repository-content-v1",
          mapping_version: "storybook-v1",
        },
      ],
    },
  ],
};
export const landscape: TechnologyLandscapeView & {
  items: [
    TechnologyLandscapeView["items"][number] & {
      projects: [TechnologyLandscapeView["items"][number]["projects"][number]];
    },
  ];
} = {
  organization_id: organizationId,
  evaluated_at: "2026-10-08T10:00:00Z",
  inactivity_months: 9,
  filters: {
    view: "grouped",
    offset: 0,
    limit: 128,
    project_offset: 0,
    project_limit: 128,
    include_history: false,
    include_inactive: false,
    include_proposed: true,
  },
  total: 1,
  items: [
    {
      technology: technologies[0],
      project_count: 1,
      proposed_project_count: 0,
      decision: null,
      projects: [
        {
          project_id: projects[0].project_id,
          name: projects[0].name,
          activity: "active",
          source_availability: "available",
          usage: {
            schema_version: 1,
            organization_id: organizationId,
            relation_id: "relation_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
            project_id: projects[0].project_id,
            technology_id: technologies[0].technology_id,
            state: "current",
            revision: 1,
            facts: [
              {
                context: "production",
                version: "0.115",
                version_kind: "declared_range",
                review: "confirmed",
                freshness: "current",
                evidence: scan.findings[0].evidence,
              },
            ],
          },
        },
      ],
    },
  ],
};
