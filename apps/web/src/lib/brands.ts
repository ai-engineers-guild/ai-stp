/**
 * Nominal branded identifiers. Prevents bare-string duck typing (coding-rules).
 */

declare const brand: unique symbol;

type Brand<T, B extends string> = T & { readonly [brand]: B };

export type AccountId = Brand<string, "AccountId">;
export type ComponentId = Brand<string, "ComponentId">;
export type SetupId = Brand<string, "SetupId">;
export type DeviceId = Brand<string, "DeviceId">;
export type VersionId = Brand<string, "VersionId">;
export type CursorToken = Brand<string, "CursorToken">;
export type OperationId = Brand<string, "OperationId">;
export type ETag = Brand<string, "ETag">;

const ACCOUNT_RE = /^account_[0-7][0-9A-HJKMNP-TV-Z]{25}$/;
const COMPONENT_RE = /^component_[0-7][0-9A-HJKMNP-TV-Z]{25}$/;
const SETUP_RE = /^setup_[0-7][0-9A-HJKMNP-TV-Z]{25}$/;
const DEVICE_RE = /^device_[0-7][0-9A-HJKMNP-TV-Z]{25}$/;

export function asAccountId(value: string): AccountId {
  if (!ACCOUNT_RE.test(value)) {
    throw new Error("invalid AccountId");
  }
  return value as AccountId;
}

export function tryAsAccountId(value: string): AccountId | null {
  return ACCOUNT_RE.test(value) ? (value as AccountId) : null;
}

export function asComponentId(value: string): ComponentId {
  if (!COMPONENT_RE.test(value)) {
    throw new Error("invalid ComponentId");
  }
  return value as ComponentId;
}

export function tryAsComponentId(value: string): ComponentId | null {
  return COMPONENT_RE.test(value) ? (value as ComponentId) : null;
}

export function asSetupId(value: string): SetupId {
  if (!SETUP_RE.test(value)) {
    throw new Error("invalid SetupId");
  }
  return value as SetupId;
}

export function tryAsSetupId(value: string): SetupId | null {
  return SETUP_RE.test(value) ? (value as SetupId) : null;
}

export function asDeviceId(value: string): DeviceId {
  if (!DEVICE_RE.test(value)) {
    throw new Error("invalid DeviceId");
  }
  return value as DeviceId;
}

export function asVersionId(value: string): VersionId {
  if (value.length === 0 || value.length > 32) {
    throw new Error("invalid VersionId");
  }
  return value as VersionId;
}

export function asCursorToken(value: string): CursorToken {
  return value as CursorToken;
}

export function asOperationId(value: string): OperationId {
  return value as OperationId;
}

export function asETag(value: string): ETag {
  return value as ETag;
}
