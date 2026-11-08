// Generated from canonical CLI schemas; do not edit.
export const personalOwnershipSchema = {
  additionalProperties: false,
  description:
    "Retained local authoring identity, independent of any selected company view.",
  properties: {
    kind: { const: "personal", title: "Kind", type: "string" },
    native_account_id: {
      pattern: "^account_[0-7][0-9A-HJKMNP-TV-Z]{25}$",
      title: "Native Account Id",
      type: "string",
    },
    native_device_id: {
      pattern: "^device_[0-7][0-9A-HJKMNP-TV-Z]{25}$",
      title: "Native Device Id",
      type: "string",
    },
  },
  required: ["kind", "native_account_id", "native_device_id"],
  title: "NativePersonalTaskOwnership",
  type: "object",
} as const;
export const taskStates = [
  "planned",
  "blocked",
  "running",
  "completed",
  "failed",
  "cancelled",
] as const;
export const taskIntents = [
  "inspect",
  "initialize",
  "install",
  "change",
  "author",
  "switch",
  "account",
  "publish",
  "technology",
] as const;
export const taskActors = ["human", "external"] as const;
