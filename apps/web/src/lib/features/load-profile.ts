import { readFileSync, statSync } from "node:fs";
import path from "node:path";

import { JSON_SCHEMA, load } from "js-yaml";

import { FEATURE_KEYS, type FeatureKey, type FeatureSet, featureEnvName } from "./definitions";
import { featureConfigSchema } from "./schema";

const MAX_CONFIG_BYTES = 32 * 1024;

export type FeatureBuildEnvironment = Readonly<Record<string, string | undefined>>;

export type ResolvedFeatureProfile = {
  profile: string;
  features: FeatureSet;
};

function configPath(root: string): string {
  return path.join(root, "config", "features.yaml");
}

function parseBooleanOverride(name: string, value: string): boolean {
  if (value === "true") return true;
  if (value === "false") return false;
  throw new Error(`${name} must be exactly true or false`);
}

function rejectUnknownOverrides(env: FeatureBuildEnvironment): void {
  const allowed = new Set(FEATURE_KEYS.map(featureEnvName));
  const unknown = Object.keys(env)
    .filter((name) => name.startsWith("AI_STP_FEATURE_") && !allowed.has(name as never))
    .sort();
  if (unknown.length > 0) {
    throw new Error(`Unknown web feature override: ${unknown.join(", ")}`);
  }
}

export function loadFeatureConfig(webRoot: string) {
  const source = configPath(webRoot);
  const size = statSync(source).size;
  if (size > MAX_CONFIG_BYTES) {
    throw new Error(`Web feature config exceeds ${String(MAX_CONFIG_BYTES)} bytes`);
  }
  const raw = readFileSync(source, "utf8");
  let value: unknown;
  try {
    value = load(raw, { json: false, schema: JSON_SCHEMA });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Invalid web feature YAML: ${message}`, { cause: error });
  }
  const parsed = featureConfigSchema.safeParse(value);
  if (!parsed.success) {
    const details = parsed.error.issues
      .map((issue) => `${issue.path.join(".")}: ${issue.message}`)
      .join("; ");
    throw new Error(`Invalid web feature config: ${details}`);
  }
  return parsed.data;
}

export function resolveFeatureProfile(
  webRoot: string,
  env: FeatureBuildEnvironment,
): ResolvedFeatureProfile {
  rejectUnknownOverrides(env);
  const config = loadFeatureConfig(webRoot);
  const profile = env["AI_STP_WEB_PROFILE"] ?? config.default_profile;
  const selected = config.profiles[profile];
  if (!selected) {
    throw new Error(`Unknown AI_STP_WEB_PROFILE ${JSON.stringify(profile)}`);
  }
  const features = Object.fromEntries(
    FEATURE_KEYS.map((key: FeatureKey) => {
      const name = featureEnvName(key);
      const override = env[name];
      return [
        key,
        override === undefined || override === ""
          ? selected[key]
          : parseBooleanOverride(name, override),
      ];
    }),
  ) as Record<FeatureKey, boolean>;
  return { profile, features };
}
