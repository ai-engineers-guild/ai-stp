import { notFound } from "next/navigation";

import { COMPILED_FEATURES } from "@/lib/features/compiled";
import type { FeatureKey } from "@/lib/features/definitions";

export function isFeatureEnabled(key: FeatureKey): boolean {
  return COMPILED_FEATURES[key];
}

export function requireFeature(key: FeatureKey): void {
  if (!isFeatureEnabled(key)) notFound();
}
