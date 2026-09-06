/* eslint-disable max-lines -- machine catalog presenters stay in one owner module */
import {
  code,
  field,
  heading,
  link,
  list,
  paragraph,
  type MachineBlock,
  type MachineDocument,
} from "@/lib/projection/machine-document";
import { registryCommand } from "@/lib/cli-copy";
import type { PublicObjectFacts } from "@/lib/projection/page-facts";
import { namedHarnesses } from "@/lib/catalog-harnesses";
import type { DocsNavNode } from "@/lib/docs-nav";
import { usageFromCounts, usageMachineFields } from "@/lib/projection/usage-fields";

type TrustLike = {
  trust_lane: string;
  author_verified: boolean;
  component_verified: boolean;
};

type ComponentSummaryLike = {
  stable_id: string;
  publisher_id: string;
  latest_name: string;
  latest_description: string;
  latest_version: string;
  latest_harness_id: string;
  latest_harness_ids?: string[];
  latest_component_type: string;
  latest_lifecycle: string;
  latest_tags: string[];
  latest_trust: TrustLike;
  latest_published_at: string;
  likes_count: number;
  usage_metrics?: {
    detail_views_count: number;
    artifact_downloads_count: number;
  } | null;
};

type SetupSummaryLike = {
  stable_id: string;
  publisher_id: string;
  latest_name: string;
  latest_description: string;
  latest_version: string;
  latest_harness_id: string;
  latest_purpose: string;
  // Nullable since ADR-0130: a role has no source, so a first-party setup
  // carries none and the card shows the absence instead of an invented value.
  latest_target_role: string | null;
  latest_posture: string | null;
  latest_lifecycle: string;
  latest_tags: string[];
  latest_trust: TrustLike;
  latest_published_at: string;
  likes_count: number;
  usage_metrics?: {
    detail_views_count: number;
    artifact_downloads_count: number;
  } | null;
};

type Labels = {
  yes: string;
  no: string;
  stableId: string;
  version: string;
  digest: string;
  harness: string;
  trustLane: string;
  authorVerified: string;
  componentVerified: string;
  install: string;
  type?: string;
  purpose?: string;
  targetRole?: string;
  posture?: string;
  publisher?: string;
  tags?: string;
  lifecycle?: string;
  projectionKind?: string;
  dependencies?: string;
  license?: string;
  publishedAt?: string;
  requiresCredentials?: string;
  requiresAuthorization?: string;
  requiredEnv?: string;
  requiresCapabilities?: string;
  compatibility?: string;
  checks?: string;
  githubStars?: string;
  detailViews?: string;
  artifactDownloads?: string;
  none?: string;
};

function yesNo(value: boolean, labels: Labels): string {
  return value ? labels.yes : labels.no;
}

export function presentLanding(input: {
  title: string;
  subtitle: string;
  browseCatalog: string;
  signIn?: string;
  installCommand: string;
  installHeading: string;
  docsHref?: string;
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.title),
    paragraph(input.subtitle),
    link(input.browseCatalog, "/catalog"),
    link("Documentation", input.docsHref ?? "/docs"),
    heading(2, input.installHeading),
    code(input.installCommand),
  ];
  if (input.signIn) {
    doc.push(link(input.signIn, "/login"));
  }
  return doc;
}

export function presentCatalog(input: {
  title: string;
  subtitle: string;
  components: ComponentSummaryLike[];
  setups: SetupSummaryLike[];
  labels: Labels;
  emptyMessage?: string;
  queryFields?: readonly (readonly [string, string])[];
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.title),
    paragraph(input.subtitle),
    link("Home", "/"),
  ];
  for (const [name, value] of input.queryFields ?? []) {
    doc.push(field(name, value));
  }

  if (input.components.length === 0 && input.setups.length === 0) {
    if (input.emptyMessage) {
      doc.push(paragraph(input.emptyMessage));
    }
    return doc;
  }

  if (input.setups.length > 0) {
    doc.push(heading(2, "Setups"));
    for (const item of input.setups) {
      doc.push(
        link(`${item.latest_name}@${item.latest_version}`, `/catalog/setups/${item.stable_id}`),
      );
      doc.push(
        field(input.labels.stableId, item.stable_id),
        field(input.labels.harness, item.latest_harness_id),
        field(input.labels.trustLane, item.latest_trust.trust_lane),
        field(input.labels.authorVerified, yesNo(item.latest_trust.author_verified, input.labels)),
        field(
          input.labels.componentVerified,
          yesNo(item.latest_trust.component_verified, input.labels),
        ),
      );
    }
  }

  if (input.components.length > 0) {
    doc.push(heading(2, "Components"));
    for (const item of input.components) {
      doc.push(
        link(`${item.latest_name}@${item.latest_version}`, `/catalog/components/${item.stable_id}`),
      );
      doc.push(
        field(input.labels.stableId, item.stable_id),
        field(input.labels.type ?? "type", item.latest_component_type),
        field(input.labels.harness, namedHarnesses(item).join(", ")),
        field(input.labels.trustLane, item.latest_trust.trust_lane),
        field(input.labels.authorVerified, yesNo(item.latest_trust.author_verified, input.labels)),
        field(
          input.labels.componentVerified,
          yesNo(item.latest_trust.component_verified, input.labels),
        ),
      );
    }
  }

  return doc;
}

export function presentComponentDetail(input: {
  facts: PublicObjectFacts;
  labels: Labels;
}): MachineDocument {
  return presentComponentObject(input.facts, input.labels, "detail");
}

export function presentSetupDetail(input: {
  summary: SetupSummaryLike;
  passportDigest: string | null;
  labels: Labels;
  sourceUrl?: string | null;
  countryCodes?: string[];
  services?: string[];
}): MachineDocument {
  const { summary, passportDigest, labels } = input;
  const install = registryCommand(summary.stable_id, summary.latest_version);
  return [
    heading(1, `${summary.latest_name}@${summary.latest_version}`),
    paragraph(summary.latest_description),
    link("Catalog", "/catalog"),
    link("Publisher", `/publishers/${summary.publisher_id}`),
    ...(input.sourceUrl ? [link("GitHub", input.sourceUrl)] : []),
    field(labels.stableId, summary.stable_id),
    field(labels.version, summary.latest_version),
    field(labels.digest, passportDigest ?? ""),
    field(labels.harness, summary.latest_harness_id),
    field(labels.purpose ?? "purpose", summary.latest_purpose),
    // `?? ""` rather than omitting the row: the machine document's shape is a
    // contract, and a row that appears only sometimes is harder to read than an
    // empty value. Same convention as `digest` two lines up.
    field(labels.targetRole ?? "target_role", summary.latest_target_role ?? ""),
    field(labels.posture ?? "posture", summary.latest_posture ?? ""),
    field(labels.trustLane, summary.latest_trust.trust_lane),
    field(labels.authorVerified, yesNo(summary.latest_trust.author_verified, labels)),
    field(labels.componentVerified, yesNo(summary.latest_trust.component_verified, labels)),
    field(labels.lifecycle ?? "lifecycle", summary.latest_lifecycle),
    field(labels.publisher ?? "publisher", summary.publisher_id),
    ...(summary.latest_tags.length
      ? [field(labels.tags ?? "tags", summary.latest_tags.join(", "))]
      : []),
    ...(input.countryCodes?.length ? [field("countries", input.countryCodes.join(", "))] : []),
    ...(input.services?.length ? [field("services", input.services.join(", "))] : []),
    field(labels.install, install),
    ...usageMachineFields(summary.usage_metrics, labels),
    code(install),
  ];
}

export function presentComponentVersion(input: {
  facts: PublicObjectFacts;
  labels: Labels;
}): MachineDocument {
  return presentComponentObject(input.facts, input.labels, "version");
}

function presentComponentObject(
  facts: PublicObjectFacts,
  labels: Labels,
  kind: "detail" | "version",
): MachineDocument {
  const none = labels.none ?? "none";
  const doc: MachineDocument = [
    heading(1, `${facts.name}@${facts.version}`),
    paragraph(facts.description),
  ];
  if (kind === "version") {
    doc.push(link("Object", `/catalog/components/${facts.stableId}`));
  }
  doc.push(link("Catalog", "/catalog"));
  if (facts.publisher) {
    doc.push(link("Publisher", `/publishers/${facts.publisher}`));
  }
  if (facts.sourceLinks?.length) {
    doc.push(...facts.sourceLinks.map((item) => link(item.provider, item.href)));
  } else if (facts.sourceUrl) {
    doc.push(link("GitHub", facts.sourceUrl));
  }
  doc.push(
    field(labels.stableId, facts.stableId),
    field(labels.version, facts.version),
    field(labels.digest, facts.digest),
    field(labels.harness, facts.harness),
    field(labels.type ?? "component_type", facts.componentType ?? ""),
    field(labels.projectionKind ?? "projection_kind", facts.projectionKind ?? ""),
    field(labels.trustLane, facts.trustLane),
    field(labels.authorVerified, yesNo(facts.authorVerified, labels)),
    field(labels.componentVerified, yesNo(facts.componentVerified, labels)),
    field(
      labels.dependencies ?? "dependencies",
      facts.dependencies.length
        ? facts.dependencies.map((item) => `${item.stableId}@${item.version}`).join(", ")
        : none,
    ),
  );
  pushOptionalComponentFields(doc, facts, labels);
  if (kind === "detail") {
    for (const version of facts.versions) {
      doc.push(
        link(
          `${facts.stableId}@${version}`,
          `/catalog/components/${facts.stableId}/versions/${version}`,
        ),
      );
    }
  }
  doc.push(field(labels.install, facts.install), code(facts.install));
  return doc;
}

// eslint-disable-next-line complexity -- existing optional catalog fields
function pushOptionalComponentFields(
  doc: MachineDocument,
  facts: PublicObjectFacts,
  labels: Labels,
): void {
  const extra: MachineBlock[] = [];
  if (facts.lifecycle) extra.push(field(labels.lifecycle ?? "lifecycle", facts.lifecycle));
  if (facts.publisher) extra.push(field(labels.publisher ?? "publisher", facts.publisher));
  if (facts.tags.length) extra.push(field(labels.tags ?? "tags", facts.tags.join(", ")));
  if (facts.license) extra.push(field(labels.license ?? "license", facts.license));
  if (facts.publishedAt) extra.push(field(labels.publishedAt ?? "published_at", facts.publishedAt));
  if (facts.requiresCredentials !== undefined) {
    extra.push(
      field(
        labels.requiresCredentials ?? "requires_credentials",
        yesNo(facts.requiresCredentials, labels),
      ),
    );
  }
  if (facts.requiresAuthorization) {
    extra.push(
      field(labels.requiresAuthorization ?? "requires_authorization", facts.requiresAuthorization),
    );
  }
  if (facts.requiredEnv.length) {
    extra.push(
      field(
        labels.requiredEnv ?? "required_env",
        facts.requiredEnv.map((item) => `${item.name} — ${item.purpose}`).join(", "),
      ),
    );
  }
  if (facts.requiresCapabilities.length) {
    extra.push(
      field(
        labels.requiresCapabilities ?? "requires_capabilities",
        facts.requiresCapabilities.join(", "),
      ),
    );
  }
  if (facts.compatibilityEvidence.length) {
    extra.push(
      field(labels.compatibility ?? "compatibility", facts.compatibilityEvidence.join(", ")),
    );
  }
  if (facts.countryCodes.length) {
    extra.push(field("countries", facts.countryCodes.join(", ")));
    extra.push(...facts.countryCodes.map((code) => link(code, `/countries/${code}`)));
  }
  if (facts.services.length) {
    extra.push(field("services", facts.services.join(", ")));
    extra.push(...facts.services.map((domain) => link(domain, `/services/${domain}`)));
  }
  if (facts.checksSummary) {
    extra.push(field(labels.checks ?? "safety_checks", facts.checksSummary));
  }
  if (facts.githubStars !== null && facts.githubStars !== undefined) {
    extra.push(field(labels.githubStars ?? "github_stars", String(facts.githubStars)));
  }
  if (facts.githubArchived) extra.push(field("github_archived", labels.yes));
  extra.push(
    ...usageMachineFields(
      usageFromCounts(facts.detailViewsCount, facts.artifactDownloadsCount),
      labels,
    ),
  );
  doc.push(...extra);
}

export function presentSetupVersion(input: {
  stableId: string;
  name: string;
  version: string;
  description: string;
  digest: string;
  harness: string;
  purpose: string;
  targetRole: string | null;
  posture: string | null;
  trust: TrustLike;
  ownerId: string;
  tags: string[];
  labels: Labels;
  usage?: { detail_views_count: number; artifact_downloads_count: number } | null;
}): MachineDocument {
  const install = registryCommand(input.stableId, input.version);
  return [
    heading(1, `${input.name}@${input.version}`),
    paragraph(input.description),
    link("Object", `/catalog/setups/${input.stableId}`),
    link("Catalog", "/catalog"),
    field(input.labels.stableId, input.stableId),
    field(input.labels.version, input.version),
    field(input.labels.digest, input.digest),
    field(input.labels.harness, input.harness),
    field(input.labels.purpose ?? "purpose", input.purpose),
    field(input.labels.targetRole ?? "target_role", input.targetRole ?? ""),
    field(input.labels.posture ?? "posture", input.posture ?? ""),
    field(input.labels.trustLane, input.trust.trust_lane),
    field(input.labels.authorVerified, yesNo(input.trust.author_verified, input.labels)),
    field(input.labels.componentVerified, yesNo(input.trust.component_verified, input.labels)),
    field(input.labels.publisher ?? "publisher", input.ownerId),
    ...(input.tags.length ? [field(input.labels.tags ?? "tags", input.tags.join(", "))] : []),
    ...usageMachineFields(input.usage, input.labels),
    field(input.labels.install, install),
    code(install),
  ];
}

export function presentPublisher(input: {
  title: string;
  accountId: string;
  displayName: string | null;
  bio: string | null;
  links: ReadonlyArray<{ label: string; url: string }>;
  componentIds: string[];
  setupIds: string[];
  emptyProfile: string;
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.displayName ?? input.title),
    field("account_id", input.accountId),
    link("Catalog", "/catalog"),
  ];
  if (input.bio) {
    doc.push(paragraph(input.bio));
  } else if (input.componentIds.length === 0 && input.setupIds.length === 0) {
    doc.push(paragraph(input.emptyProfile));
  }
  for (const item of input.links) {
    doc.push(link(item.label, item.url));
  }
  if (input.componentIds.length > 0) {
    doc.push(heading(2, "Components"));
    doc.push(
      list(input.componentIds.map((id) => id)),
      ...input.componentIds.map((id) => link(id, `/catalog/components/${id}`)),
    );
  }
  if (input.setupIds.length > 0) {
    doc.push(heading(2, "Setups"));
    doc.push(...input.setupIds.map((id) => link(id, `/catalog/setups/${id}`)));
  }
  return doc;
}

export function presentDocs(input: {
  title: string;
  description: string | null;
  bodyText: string;
  nav: readonly DocsNavNode[];
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.title),
    link("Home", "/"),
    link("Catalog", "/catalog"),
  ];
  if (input.description) {
    doc.push(paragraph(input.description));
  }
  if (input.nav.length > 0) {
    doc.push(heading(2, "Pages"));
    pushDocsNav(doc, input.nav, 3);
  }
  if (input.bodyText.trim()) {
    doc.push(heading(2, "Content"));
    doc.push(paragraph(input.bodyText.trim()));
  }
  return doc;
}

function pushDocsNav(doc: MachineDocument, nodes: readonly DocsNavNode[], level: number): void {
  for (const node of nodes) {
    if (node.children?.length) {
      doc.push(heading(Math.min(level, 6), node.title));
      if (node.href) {
        doc.push(link(node.title, node.href));
      }
      pushDocsNav(doc, node.children, level + 1);
      continue;
    }
    if (node.href) {
      doc.push(link(node.title, node.href));
    }
  }
}

export function presentLegal(input: {
  title: string;
  body: string;
  version: string;
  effective: string;
  language: string;
  versionLabel: string;
  effectiveLabel: string;
  languageLabel: string;
  policyLinks?: readonly { title: string; href: string }[];
}): MachineDocument {
  return [
    heading(1, input.title),
    link("Home", "/"),
    field(input.versionLabel, input.version),
    field(input.effectiveLabel, input.effective),
    field(input.languageLabel, input.language),
    paragraph(input.body),
    ...(input.policyLinks ?? []).map((item) => link(item.title, item.href)),
  ];
}

/** Static platform context shared by /llms-full.txt (REQ-3608). */
export function presentPlatformContext(input: { docsHref?: string } = {}): MachineDocument {
  return [
    heading(1, "ai_stp machine context"),
    paragraph(
      "ai_stp creates, validates, stores, selects and installs complete configurations for AI coding harnesses. A setup belongs to exactly one harness and pins exact component versions. Supported component kinds are instruction, skill, mcp, hook, command, agent, plugin, setting and cli.",
    ),
    paragraph(
      "Primary support: Claude Code and Codex. Beta support: Pi, OpenCode and Grok Build. Unknown harnesses use the restricted undefined mode.",
    ),
    paragraph(
      "Trust lines are authoritative, experimental and local_owner_or_pinned. author_verified and component_verified are independent. Verified authorship never proves content safety. A foreign unverified object requires explicit consent and cannot participate in automatic installation.",
    ),
    paragraph(
      "The agent interprets findings and proposes composition. The CLI and core discover facts, enforce mechanical constraints, store local state and build deterministic native packages. Only the public provider for a harness writes its final state. The active target is never modified in place.",
    ),
    paragraph(
      "Public web pages expose only public projections. Secrets, tokens, private records, object-store keys and device details are never machine-discovery content.",
    ),
    heading(2, "Public routes"),
    link("Home", "/"),
    link("Catalog", "/catalog"),
    link("Documentation", input.docsHref ?? "/docs"),
    link("Privacy", "/legal/privacy"),
  ];
}

export type MachineEntry = {
  title: string;
  href?: string;
  fields?: readonly (readonly [string, string])[];
};

/**
 * Generic page document. Every route has a machine representation, so pages
 * without a domain-specific presenter describe themselves with their heading,
 * summary, own fields, listed records and outgoing links (REQ-3611).
 */
export function presentPage(input: {
  title: string;
  summary?: string;
  fields?: readonly (readonly [string, string])[];
  entries?: readonly MachineEntry[];
  sections?: readonly { heading: string; entries?: readonly MachineEntry[]; text?: string }[];
  links?: readonly (readonly [string, string])[];
  emptyMessage?: string;
}): MachineDocument {
  const doc: MachineDocument = [heading(1, input.title)];
  if (input.summary) doc.push(paragraph(input.summary));
  for (const [name, value] of input.fields ?? []) doc.push(field(name, value));

  const pushEntries = (entries: readonly MachineEntry[]) => {
    for (const entry of entries) {
      if (entry.href) doc.push(link(entry.title, entry.href));
      else doc.push(heading(3, entry.title));
      for (const [name, value] of entry.fields ?? []) doc.push(field(name, value));
    }
  };

  if (input.entries?.length) pushEntries(input.entries);
  else if (input.entries && input.emptyMessage) doc.push(paragraph(input.emptyMessage));

  for (const section of input.sections ?? []) {
    doc.push(heading(2, section.heading));
    if (section.text) doc.push(paragraph(section.text));
    if (section.entries?.length) pushEntries(section.entries);
    else if (section.entries && input.emptyMessage) doc.push(paragraph(input.emptyMessage));
  }

  for (const [text, href] of input.links ?? []) doc.push(link(text, href));
  return doc;
}
