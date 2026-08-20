import {
  field,
  heading,
  link,
  paragraph,
  type MachineDocument,
} from "@/lib/projection/machine-document";

/**
 * Machine documents for the account and owner sections. A private page shows
 * the same records to the same subject as its human twin; the projection
 * changes the form, never the access (SPEC-036, REQ-3611).
 */

type Bool = { yes: string; no: string };

const flag = (value: boolean, labels: Bool) => (value ? labels.yes : labels.no);

export function presentAccount(input: {
  title: string;
  accountId: string;
  identities: ReadonlyArray<{
    provider: string;
    displayName: string | null;
    linkedAt: string;
  }>;
  labels: {
    accountId: string;
    signInMethods: string;
    provider: string;
    linkedAt: string;
    displayName: string;
  };
  links: ReadonlyArray<readonly [string, string]>;
}): MachineDocument {
  const doc: MachineDocument = [
    heading(1, input.title),
    field("account_id", input.accountId),
    heading(2, input.labels.signInMethods),
  ];
  for (const identity of input.identities) {
    doc.push(field(input.labels.provider, identity.provider));
    if (identity.displayName) {
      doc.push(field(input.labels.displayName, identity.displayName));
    }
    doc.push(field(input.labels.linkedAt, identity.linkedAt));
  }
  for (const [text, href] of input.links) {
    doc.push(link(text, href));
  }
  return doc;
}

export function presentDevices(input: {
  title: string;
  subtitle: string;
  emptyMessage: string;
  devices: ReadonlyArray<{
    deviceId: string;
    deviceType: string;
    state: string;
    lastActiveAt: string;
    location: string | null;
    current: boolean;
  }>;
  labels: Bool & {
    deviceType: string;
    state: string;
    lastConnected: string;
    approximateLocation: string;
    locationUnknown: string;
    current: string;
  };
}): MachineDocument {
  const doc: MachineDocument = [heading(1, input.title), paragraph(input.subtitle)];
  if (input.devices.length === 0) {
    doc.push(paragraph(input.emptyMessage));
    return doc;
  }
  for (const device of input.devices) {
    doc.push(heading(3, device.deviceId));
    doc.push(field(input.labels.deviceType, device.deviceType));
    doc.push(field(input.labels.state, device.state));
    doc.push(field(input.labels.lastConnected, device.lastActiveAt));
    doc.push(
      field(input.labels.approximateLocation, device.location ?? input.labels.locationUnknown),
    );
    doc.push(field(input.labels.current, flag(device.current, input.labels)));
  }
  return doc;
}

export function presentOwnerObjects(input: {
  title: string;
  subtitle: string;
  emptyMessage: string;
  items: ReadonlyArray<{
    name: string;
    stableId: string;
    objectKind: string;
    latestVersion: string | null;
    lifecycle: string;
    authorVerified: boolean;
    componentVerified: boolean;
    updatedAt: string;
  }>;
  labels: Bool & {
    stableId: string;
    objectKind: string;
    version: string;
    lifecycle: string;
    authorVerified: string;
    componentVerified: string;
    updatedAt: string;
  };
}): MachineDocument {
  const doc: MachineDocument = [heading(1, input.title), paragraph(input.subtitle)];
  if (input.items.length === 0) {
    doc.push(paragraph(input.emptyMessage));
    return doc;
  }
  for (const item of input.items) {
    doc.push(link(item.name, `/objects/${item.objectKind}/${item.stableId}`));
    doc.push(field(input.labels.stableId, item.stableId));
    doc.push(field(input.labels.objectKind, item.objectKind));
    doc.push(field(input.labels.version, item.latestVersion ?? "-"));
    doc.push(field(input.labels.lifecycle, item.lifecycle));
    doc.push(field(input.labels.authorVerified, flag(item.authorVerified, input.labels)));
    doc.push(field(input.labels.componentVerified, flag(item.componentVerified, input.labels)));
    doc.push(field(input.labels.updatedAt, item.updatedAt));
  }
  return doc;
}

export function presentAccess(input: {
  title: string;
  subtitle: string;
  invitations: ReadonlyArray<{
    invitationId: string;
    objectKind: string;
    stableId: string;
    major: number;
    state: string;
    expiresAt: string;
  }>;
  grants: ReadonlyArray<{
    grantId: string;
    objectKind: string;
    stableId: string;
    major: number;
    grantee: string;
    revokedAt: string | null;
  }>;
  labels: {
    invitations: string;
    grants: string;
    emptyInvitations: string;
    emptyGrants: string;
    stableId: string;
    kind: string;
    major: string;
    state: string;
    expires: string;
    grantee: string;
    revoked: string;
  };
}): MachineDocument {
  const doc: MachineDocument = [heading(1, input.title), paragraph(input.subtitle)];

  doc.push(heading(2, input.labels.invitations));
  if (input.invitations.length === 0) {
    doc.push(paragraph(input.labels.emptyInvitations));
  }
  for (const item of input.invitations) {
    doc.push(link(item.invitationId, `/invitations/${item.invitationId}`));
    doc.push(field(input.labels.kind, item.objectKind));
    doc.push(field(input.labels.stableId, item.stableId));
    doc.push(field(input.labels.major, String(item.major)));
    doc.push(field(input.labels.state, item.state));
    doc.push(field(input.labels.expires, item.expiresAt));
  }

  doc.push(heading(2, input.labels.grants));
  if (input.grants.length === 0) {
    doc.push(paragraph(input.labels.emptyGrants));
  }
  for (const item of input.grants) {
    doc.push(heading(3, item.grantId));
    doc.push(field(input.labels.kind, item.objectKind));
    doc.push(field(input.labels.stableId, item.stableId));
    doc.push(field(input.labels.major, String(item.major)));
    doc.push(field(input.labels.grantee, item.grantee));
    if (item.revokedAt) {
      doc.push(field(input.labels.revoked, item.revokedAt));
    }
  }
  return doc;
}

export function presentReportCases(input: {
  title: string;
  subtitle: string;
  emptyMessage: string;
  detailHref?: (caseId: string) => string;
  cases: ReadonlyArray<{
    caseId: string;
    objectKind: string;
    stableId: string;
    version: string;
    state: string;
    vulnerability: boolean;
    createdAt: string;
  }>;
  labels: Bool & {
    objectKind: string;
    stableId: string;
    version: string;
    state: string;
    vulnerability: string;
    createdAt: string;
  };
}): MachineDocument {
  const doc: MachineDocument = [heading(1, input.title), paragraph(input.subtitle)];
  if (input.cases.length === 0) {
    doc.push(paragraph(input.emptyMessage));
    return doc;
  }
  for (const item of input.cases) {
    const href = input.detailHref?.(item.caseId);
    doc.push(href ? link(item.caseId, href) : heading(3, item.caseId));
    doc.push(field(input.labels.objectKind, item.objectKind));
    doc.push(field(input.labels.stableId, item.stableId));
    doc.push(field(input.labels.version, item.version));
    doc.push(field(input.labels.state, item.state));
    doc.push(field(input.labels.vulnerability, flag(item.vulnerability, input.labels)));
    doc.push(field(input.labels.createdAt, item.createdAt));
  }
  return doc;
}
