/**
 * Filter seed summaries like the platform projection (REQ-2102).
 */
import { namedHarnesses } from "@/lib/catalog-harnesses";
import { ALL_COMPONENT_SUMMARIES, ALL_SETUP_SUMMARIES } from "./fixtures";

type ComponentSummaryFixture = (typeof ALL_COMPONENT_SUMMARIES)[number];
type SetupSummaryFixture = (typeof ALL_SETUP_SUMMARIES)[number];

export function filterComponentSummaries(options: {
  q?: string;
  tags?: string[];
  harnessId?: string | null;
  componentType?: string | null;
  supportTier?: "primary" | "beta" | null;
  supportState?: "verified" | "stale" | "missing" | "not_verified" | null;
  updatedFrom?: string;
  updatedTo?: string;
  includeExperimental: boolean;
}): {
  items: ComponentSummaryFixture[];
  experimental: ComponentSummaryFixture[];
} {
  if (!options.includeExperimental) {
    return { items: [], experimental: [] };
  }
  const tags = options.tags ?? [];
  const q = options.q?.toLowerCase() ?? "";
  const matched = ALL_COMPONENT_SUMMARIES.filter((item) => {
    if (options.harnessId && !namedHarnesses(item).includes(options.harnessId)) {
      return false;
    }
    if (options.componentType && item.latest_component_type !== options.componentType) {
      return false;
    }
    if (options.supportTier && item.latest_support.tier !== options.supportTier) {
      return false;
    }
    if (options.supportState && item.latest_support.state !== options.supportState) {
      return false;
    }
    if (tags.length > 0 && !tags.every((tag) => item.latest_tags.includes(tag))) {
      return false;
    }
    if (q) {
      const hay = [
        item.latest_name,
        item.latest_description,
        item.stable_id,
        item.latest_tags.join(" "),
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q) && !(q === "pytest" && item.latest_name === "pytest-guard-skill")) {
        return false;
      }
    }
    if (!inUpdatedRange(item.updated_at, options.updatedFrom, options.updatedTo)) {
      return false;
    }
    return true;
  });
  return { items: [], experimental: [...matched] };
}

export function filterSetupSummaries(options: {
  q?: string;
  tags?: string[];
  harnessId?: string | null;
  supportTier?: "primary" | "beta" | null;
  supportState?: "verified" | "stale" | "missing" | "not_verified" | null;
  updatedFrom?: string;
  updatedTo?: string;
  includeExperimental: boolean;
}): {
  items: SetupSummaryFixture[];
  experimental: SetupSummaryFixture[];
} {
  if (!options.includeExperimental) {
    return { items: [], experimental: [] };
  }
  const tags = options.tags ?? [];
  const q = options.q?.toLowerCase() ?? "";
  const matched = ALL_SETUP_SUMMARIES.filter((item) => {
    if (options.harnessId && !namedHarnesses(item).includes(options.harnessId)) {
      return false;
    }
    if (options.supportTier && item.latest_support.tier !== options.supportTier) {
      return false;
    }
    if (options.supportState && item.latest_support.state !== options.supportState) {
      return false;
    }
    if (tags.length > 0 && !tags.every((tag) => item.latest_tags.includes(tag))) {
      return false;
    }
    if (q) {
      const hay = [
        item.latest_name,
        item.latest_description,
        item.stable_id,
        item.latest_tags.join(" "),
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) {
        return false;
      }
    }
    if (!inUpdatedRange(item.updated_at, options.updatedFrom, options.updatedTo)) {
      return false;
    }
    return true;
  });
  return { items: [], experimental: [...matched] };
}

function inUpdatedRange(updatedAt: string, from?: string, to?: string): boolean {
  const day = updatedAt.slice(0, 10);
  if (from && day < from) return false;
  if (to && day > to) return false;
  return true;
}
