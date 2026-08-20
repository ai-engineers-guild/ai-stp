import { describe, expect, it } from "vitest";

import { DEVICE_SUMMARY_FIELDS } from "@/lib/api/device-summary-fields";
import { deviceList } from "@/mocks/fixtures";

const FORBIDDEN_SUMMARY_KEYS = [
  "absolute_path",
  "env",
  "environment",
  "private_key",
  "path",
  "secret",
];

describe("device summary allowlist (REQ-2304)", () => {
  it("pins exactly the closed allowlist fields", () => {
    expect([...DEVICE_SUMMARY_FIELDS].sort()).toEqual(
      [
        "architecture",
        "detected_harnesses",
        "display_name",
        "operating_system",
        "summary_updated_at",
        "toolchain_profile_version",
      ].sort(),
    );
  });

  it("fixture summary only contains allowlisted keys plus schema_version", () => {
    const summary = deviceList.items[0]?.summary;
    expect(summary).toBeTruthy();
    if (!summary) {
      return;
    }
    const keys = Object.keys(summary);
    for (const key of keys) {
      if (key === "schema_version") {
        continue;
      }
      expect(DEVICE_SUMMARY_FIELDS).toContain(key);
    }
    for (const forbidden of FORBIDDEN_SUMMARY_KEYS) {
      expect(keys).not.toContain(forbidden);
    }
  });
});
