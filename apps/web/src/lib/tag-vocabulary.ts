/**
 * Closed tag facet list for catalog filters (ADR-0024, docs/contracts/tag-vocabulary.md).
 * Canonical ids only — display names come from i18n when needed. Facets mirror
 * the first-party seed vocabulary in tests.support.catalog_seed.SEED_TAG_VOCABULARY.
 */

import { ComponentType, HarnessId } from "@/lib/api/generated/types.gen";

export const TAG_FACETS = [
  "python",
  "tests",
  "code-review",
  "documentation",
  "devops",
  "security",
  "refactor",
  "github",
  "planning",
  "release",
] as const;

export const MAX_TAGS = 10;
export const MAX_TAG_LENGTH = 32;

export type TagFacet = (typeof TAG_FACETS)[number];

/** Harness ids offered in catalog filter dropdowns (ADR-0003). */
export const HARNESS_FACETS: readonly HarnessId[] = Object.values(HarnessId);

export type HarnessFacet = (typeof HARNESS_FACETS)[number];

/** Component type taxonomy for catalog filter dropdowns. */
export const COMPONENT_TYPE_FACETS: readonly ComponentType[] = Object.values(ComponentType);

export type ComponentTypeFacet = (typeof COMPONENT_TYPE_FACETS)[number];

const TAG_ID_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export function isTagFacet(value: string): value is TagFacet {
  return (TAG_FACETS as readonly string[]).includes(value);
}

export function isHarnessFacet(value: string): value is HarnessFacet {
  return (HARNESS_FACETS as readonly string[]).includes(value);
}

export function isComponentTypeFacet(value: string): value is ComponentTypeFacet {
  return (COMPONENT_TYPE_FACETS as readonly string[]).includes(value);
}

/** Validate a single tag id form (vocabulary shape, not membership). */
export function isValidTagId(value: string): boolean {
  return value.length >= 2 && value.length <= MAX_TAG_LENGTH && TAG_ID_RE.test(value);
}
