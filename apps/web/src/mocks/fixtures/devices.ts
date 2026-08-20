import { FIXTURE_TIMESTAMP } from "./identity";

export const FIXTURE_DEVICE_ID = "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z";
export const FIXTURE_DEVICE_ID_2 = "device_01JQZK7B8N4M6P2R9T5V0X3Y70";

export const deviceList = {
  schema_version: 1 as const,
  items: [
    {
      schema_version: 1 as const,
      device_id: FIXTURE_DEVICE_ID,
      state: "active" as const,
      registered_at: FIXTURE_TIMESTAMP,
      last_active_at: FIXTURE_TIMESTAMP,
      summary: {
        schema_version: 1 as const,
        display_name: "fixture-device",
        operating_system: "linux" as const,
        architecture: "x86_64" as const,
        detected_harnesses: [{ harness_id: "claude-code", version: "2.1.0" }],
        toolchain_profile_version: "mvp-full/1.0",
        summary_updated_at: FIXTURE_TIMESTAMP,
      },
      etag: 'W/"7"',
    },
    {
      schema_version: 1 as const,
      device_id: FIXTURE_DEVICE_ID_2,
      state: "active" as const,
      registered_at: FIXTURE_TIMESTAMP,
      last_active_at: FIXTURE_TIMESTAMP,
      summary: null,
      etag: 'W/"1"',
    },
  ],
  page: {
    schema_version: 1 as const,
    next_cursor: null,
    page_size: 20,
  },
};
