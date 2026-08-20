export const FEATURE_DEFINITIONS = {
  content_hub: {
    owner: "apps/web",
    issue: 267,
    kind: "deploy_surface",
  },
  saas_public_pages: {
    owner: "apps/web",
    issue: 284,
    kind: "deploy_surface",
  },
  catalog_usage_metrics: {
    owner: "apps/web",
    issue: 276,
    kind: "deploy_surface",
  },
} as const;

export type FeatureKey = keyof typeof FEATURE_DEFINITIONS;
export type FeatureSet = Readonly<Record<FeatureKey, boolean>>;

export const FEATURE_KEYS = Object.freeze(Object.keys(FEATURE_DEFINITIONS) as FeatureKey[]);

export function featureEnvName(key: FeatureKey): `AI_STP_FEATURE_${Uppercase<FeatureKey>}` {
  return `AI_STP_FEATURE_${key.toUpperCase()}` as `AI_STP_FEATURE_${Uppercase<FeatureKey>}`;
}
