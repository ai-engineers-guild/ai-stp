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
