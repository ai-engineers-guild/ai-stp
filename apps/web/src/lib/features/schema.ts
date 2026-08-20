import { z } from "zod";

import { FEATURE_KEYS } from "./definitions";

const featureShape = Object.fromEntries(FEATURE_KEYS.map((key) => [key, z.boolean()])) as Record<
  (typeof FEATURE_KEYS)[number],
  z.ZodBoolean
>;

export const featureSetSchema = z.object(featureShape).strict();

export const featureConfigSchema = z
  .object({
    schema_version: z.literal(1),
    default_profile: z.string().min(1),
    profiles: z.record(z.string().min(1), featureSetSchema),
  })
  .strict()
  .superRefine((config, ctx) => {
    if (!Object.hasOwn(config.profiles, config.default_profile)) {
      ctx.addIssue({
        code: "custom",
        path: ["default_profile"],
        message: `profile ${JSON.stringify(config.default_profile)} is not declared`,
      });
    }
  });

export type FeatureConfig = z.infer<typeof featureConfigSchema>;
