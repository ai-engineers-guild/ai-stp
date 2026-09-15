import { expect, it } from "vitest";
import { loadFeatureConfig, resolveFeatureProfile } from "@/lib/features/load-profile";

it("has no local website artifact profile: local deployment is CLI-only", () => {
  expect(loadFeatureConfig(process.cwd()).profiles).not.toHaveProperty("local");
  expect(() => resolveFeatureProfile(process.cwd(), { AI_STP_WEB_PROFILE: "local" })).toThrow(
    'Unknown AI_STP_WEB_PROFILE "local"',
  );
});
