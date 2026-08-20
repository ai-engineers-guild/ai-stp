import {
  field,
  heading,
  link,
  paragraph,
  type MachineDocument,
} from "@/lib/projection/machine-document";

type Bool = { yes: string; no: string };

const flag = (value: boolean, labels: Bool) => (value ? labels.yes : labels.no);

export function presentOwnerObjectDetail(input: {
  name: string;
  kind: string;
  stableId: string;
  versions: ReadonlyArray<{ version: string; digest: string | null }>;
  attachedDomains: readonly string[];
  labels: {
    objectKind: string;
    stableId: string;
    version: string;
    digest: string;
    viewPublic: string;
    editPresentation: string;
    versions: string;
    emptyVersions: string;
    services: string;
  };
}): MachineDocument {
  const catalogHref =
    input.kind === "setup"
      ? `/catalog/setups/${input.stableId}`
      : `/catalog/components/${input.stableId}`;
  const doc: MachineDocument = [
    heading(1, input.name),
    field(input.labels.objectKind, input.kind),
    field(input.labels.stableId, input.stableId),
    link("Objects", "/objects"),
    link(input.labels.viewPublic, catalogHref),
  ];
  if (input.kind === "component") {
    doc.push(link(input.labels.editPresentation, `/objects/component/${input.stableId}/edit`));
  }
  doc.push(heading(2, input.labels.versions));
  if (input.versions.length === 0) {
    doc.push(paragraph(input.labels.emptyVersions));
  }
  for (const item of input.versions) {
    doc.push(
      link(item.version, `/objects/${input.kind}/${input.stableId}/versions/${item.version}`),
    );
    if (item.digest) {
      doc.push(field(input.labels.digest, item.digest));
    }
  }
  if (input.attachedDomains.length > 0) {
    doc.push(heading(2, input.labels.services));
    for (const domain of input.attachedDomains) {
      doc.push(link(domain, `/services/${domain}`));
    }
  }
  return doc;
}

export function presentOwnerVersion(input: {
  name: string;
  kind: string;
  stableId: string;
  version: string;
  lifecycle: string;
  visibility: string;
  digest: string | null;
  authorVerified: boolean;
  componentVerified: boolean;
  installEligible: boolean;
  labels: Bool & {
    objectKind: string;
    stableId: string;
    version: string;
    lifecycle: string;
    visibility: string;
    digest: string;
    authorVerified: string;
    componentVerified: string;
    installEligible: string;
  };
}): MachineDocument {
  return [
    heading(1, input.name),
    link("Object", `/objects/${input.kind}/${input.stableId}`),
    link("Objects", "/objects"),
    field(input.labels.objectKind, input.kind),
    field(input.labels.stableId, input.stableId),
    field(input.labels.version, input.version),
    field(input.labels.lifecycle, input.lifecycle),
    field(input.labels.visibility, input.visibility),
    field(input.labels.digest, input.digest ?? "-"),
    field(input.labels.authorVerified, flag(input.authorVerified, input.labels)),
    field(input.labels.componentVerified, flag(input.componentVerified, input.labels)),
    field(input.labels.installEligible, flag(input.installEligible, input.labels)),
  ];
}

export function presentPublication(input: {
  title: string;
  subtitle: string;
  planId: string;
  state: string;
  objectKind: string;
  stableId: string;
  version: string;
  digest: string;
  planHash: string;
  policy: string;
  expiresAt: string;
  effects: readonly string[];
  labels: {
    planId: string;
    state: string;
    objectKind: string;
    stableId: string;
    version: string;
    digest: string;
    planHash: string;
    policy: string;
    expires: string;
    effects: string;
  };
}): MachineDocument {
  return [
    heading(1, input.title),
    paragraph(input.subtitle),
    link("Objects", "/objects"),
    field(input.labels.planId, input.planId),
    field(input.labels.state, input.state),
    field(input.labels.objectKind, input.objectKind),
    field(input.labels.stableId, input.stableId),
    field(input.labels.version, input.version),
    field(input.labels.digest, input.digest),
    field(input.labels.planHash, input.planHash),
    field(input.labels.policy, input.policy),
    field(input.labels.expires, input.expiresAt),
    field(input.labels.effects, input.effects.join(", ") || "-"),
  ];
}

export function presentInvitation(input: {
  title: string;
  subtitle: string;
  invitationId: string;
  labels: { invitationId: string };
}): MachineDocument {
  return [
    heading(1, input.title),
    paragraph(input.subtitle),
    field(input.labels.invitationId, input.invitationId),
    link("Access", "/access"),
  ];
}

export function presentStaffCase(input: {
  title: string;
  caseId: string;
  state: string;
  vulnerability: boolean;
  objectKind: string;
  stableId: string;
  version: string;
  digest: string | null;
  errorCode: string;
  harnessId: string;
  labels: Bool & {
    caseId: string;
    state: string;
    vulnerability: string;
    objectKind: string;
    stableId: string;
    version: string;
    digest: string;
    errorCode: string;
    harness: string;
  };
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.title),
    link("Staff reports", "/staff/reports"),
    field(input.labels.caseId, input.caseId),
    field(input.labels.state, input.state),
    field(input.labels.vulnerability, flag(input.vulnerability, input.labels)),
    field(input.labels.objectKind, input.objectKind),
    field(input.labels.stableId, input.stableId),
    field(input.labels.version, input.version),
    field(input.labels.digest, input.digest ?? "-"),
  ];
  if (input.errorCode) {
    doc.push(field(input.labels.errorCode, input.errorCode));
  }
  if (input.harnessId) {
    doc.push(field(input.labels.harness, input.harnessId));
  }
  return doc;
}

export function presentAccountPrivacy(input: {
  title: string;
  subtitle: string;
  showProfilePublicly: boolean;
  allowPublisherListing: boolean;
  labels: Bool & {
    showProfilePublicly: string;
    allowPublisherListing: string;
  };
}): MachineDocument {
  return [
    heading(1, input.title),
    paragraph(input.subtitle),
    link("Account", "/account"),
    field(input.labels.showProfilePublicly, flag(input.showProfilePublicly, input.labels)),
    field(input.labels.allowPublisherListing, flag(input.allowPublisherListing, input.labels)),
  ];
}

export function presentAccountProfile(input: {
  title: string;
  subtitle: string;
  displayName: string | null;
  bio: string | null;
  links: ReadonlyArray<{ label: string; url: string }>;
  labels: { displayName: string; bio: string };
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.title),
    paragraph(input.subtitle),
    link("Account", "/account"),
    link("Preview", "/account/profile/preview"),
  ];
  if (input.displayName) {
    doc.push(field(input.labels.displayName, input.displayName));
  }
  if (input.bio) {
    doc.push(field(input.labels.bio, input.bio));
  }
  for (const item of input.links) {
    doc.push(link(item.label, item.url));
  }
  return doc;
}

export function presentAccountPreview(input: {
  title: string;
  banner: string;
  displayName: string | null;
  bio: string | null;
  links: ReadonlyArray<{ label: string; url: string }>;
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.displayName ?? input.title),
    paragraph(input.banner),
    link("Account", "/account"),
    link("Edit", "/account/profile"),
  ];
  if (input.bio) {
    doc.push(paragraph(input.bio));
  }
  for (const item of input.links) {
    doc.push(link(item.label, item.url));
  }
  return doc;
}

export function presentPresentationEdit(input: {
  title: string;
  note: string;
  stableId: string;
  bio: string;
  labels: { stableId: string; bio: string };
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.title),
    paragraph(input.note),
    field(input.labels.stableId, input.stableId),
    link("Object", `/objects/component/${input.stableId}`),
    link("Objects", "/objects"),
  ];
  if (input.bio) {
    doc.push(field(input.labels.bio, input.bio));
  }
  return doc;
}
