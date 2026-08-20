/** Closed device summary allowlist (device-passport.md / REQ-2304). */
export const DEVICE_SUMMARY_FIELDS = [
  "display_name",
  "operating_system",
  "architecture",
  "detected_harnesses",
  "toolchain_profile_version",
  "summary_updated_at",
] as const;
