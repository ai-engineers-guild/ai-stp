export type EntityEditorKind =
  "profile" | "component" | "setup" | "project" | "team" | "technology";

export type EntityEditorBlock =
  "avatar" | "displayName" | "description" | "links" | "media" | "regionalServices";

export type EntityEditorConfig = {
  kind: EntityEditorKind;
  blocks: readonly EntityEditorBlock[];
  displayName: "editable" | "readonly";
  limits: {
    displayName: number;
    description: number;
    links: number;
    media: number;
  };
};

export type EntityEditorLink = { label: string; url: string };
export type EntityEditorFieldErrors = Record<string, string>;

const STANDARD_LIMITS = {
  displayName: 200,
  description: 20_000,
  links: 5,
  media: 5,
} as const;

export const ENTITY_EDITOR_CONFIGS = {
  profile: {
    kind: "profile",
    blocks: ["avatar", "displayName", "description", "links"],
    displayName: "editable",
    limits: { ...STANDARD_LIMITS, displayName: 80, description: 1_500 },
  },
  component: {
    kind: "component",
    blocks: ["displayName", "description", "media", "links"],
    displayName: "readonly",
    limits: STANDARD_LIMITS,
  },
  setup: {
    kind: "setup",
    blocks: ["displayName", "description", "media", "links"],
    displayName: "readonly",
    limits: STANDARD_LIMITS,
  },
  project: {
    kind: "project",
    blocks: ["displayName", "description", "media", "links"],
    displayName: "editable",
    limits: STANDARD_LIMITS,
  },
  team: {
    kind: "team",
    blocks: ["displayName", "description", "media", "links"],
    displayName: "editable",
    limits: STANDARD_LIMITS,
  },
  technology: {
    kind: "technology",
    blocks: ["displayName", "description", "media", "links"],
    displayName: "editable",
    limits: STANDARD_LIMITS,
  },
} as const satisfies Record<EntityEditorKind, EntityEditorConfig>;

export function validateEntityDisplayName(value: string, maxLength = STANDARD_LIMITS.displayName) {
  const trimmed = value.trim();
  if (!trimmed) return "Display name is required";
  if (trimmed.length > maxLength) return `Display name must be ${maxLength} characters or fewer`;
  return null;
}

export function validateEntityLinks(
  links: readonly EntityEditorLink[],
  max = STANDARD_LIMITS.links,
) {
  if (links.length > max) return `Add no more than ${max} links`;
  const seen = new Set<string>();
  for (const link of links) {
    if (!link.label.trim()) return "Each link needs a label";
    if (link.label.trim().length > 60) return "Link labels must be 60 characters or fewer";
    try {
      const url = new URL(link.url);
      if (url.protocol !== "https:" || url.username || url.password) return "Links must use HTTPS";
    } catch {
      return "Enter a valid HTTPS link";
    }
    if (seen.has(link.url)) return "Links must be unique";
    seen.add(link.url);
  }
  return null;
}

export function validateEntityFieldErrors(
  name: string,
  links: readonly EntityEditorLink[],
  limits: { displayName: number; links: number },
  messages: {
    displayNameRequired: string;
    displayNameTooLong: string;
    tooManyLinks: string;
    linkLabelRequired: string;
    linkLabelTooLong: string;
    linkUrl: string;
    duplicateLink: string;
  },
): EntityEditorFieldErrors {
  const errors: EntityEditorFieldErrors = {};
  const trimmedName = name.trim();
  if (!trimmedName) errors.name = messages.displayNameRequired;
  else if (trimmedName.length > limits.displayName) errors.name = messages.displayNameTooLong;
  if (links.length > limits.links) errors.links = messages.tooManyLinks;
  const seen = new Set<string>();
  links.forEach((link, index) => {
    const label = link.label.trim();
    if (!label) errors[`links.${index}.label`] = messages.linkLabelRequired;
    else if (label.length > 60) errors[`links.${index}.label`] = messages.linkLabelTooLong;
    try {
      const url = new URL(link.url);
      if (url.protocol !== "https:" || url.username || url.password)
        errors[`links.${index}.url`] = messages.linkUrl;
    } catch {
      errors[`links.${index}.url`] = messages.linkUrl;
    }
    if (seen.has(link.url)) errors[`links.${index}.url`] = messages.duplicateLink;
    seen.add(link.url);
  });
  return errors;
}
