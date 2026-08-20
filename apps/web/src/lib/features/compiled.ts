import type { FeatureSet } from "@/lib/features/definitions";

export const COMPILED_FEATURES = Object.freeze({
  content_hub: process.env.AI_STP_COMPILED_FEATURE_CONTENT_HUB === "true",
  saas_public_pages: process.env.AI_STP_COMPILED_FEATURE_SAAS_PUBLIC_PAGES === "true",
  catalog_usage_metrics: process.env.AI_STP_COMPILED_FEATURE_CATALOG_USAGE_METRICS === "true",
}) satisfies FeatureSet;

export const COMPILED_FEATURE_PROFILE = process.env.AI_STP_COMPILED_FEATURE_PROFILE ?? "unknown";
