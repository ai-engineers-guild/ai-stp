import { describe, expect, it } from "vitest";

import {
  asAccountId,
  asComponentId,
  asDeviceId,
  asSetupId,
  tryAsAccountId,
  tryAsComponentId,
  tryAsSetupId,
} from "@/lib/brands";

describe("branded ids", () => {
  it("accepts fixture-shaped ids", () => {
    expect(asAccountId("account_01JQZK7B8N4M6P2R9T5V0X3Y7Z")).toBe(
      "account_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    );
    expect(asComponentId("component_01JQZK7B8N4M6P2R9T5V0X3Y7Z")).toBe(
      "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    );
    expect(asSetupId("setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z")).toBe("setup_01JQZK7B8N4M6P2R9T5V0X3Y7Z");
    expect(asDeviceId("device_01JQZK7B8N4M6P2R9T5V0X3Y7Z")).toBe(
      "device_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    );
  });

  it("rejects bare strings that are not ids", () => {
    expect(() => asAccountId("not-an-id")).toThrow();
    expect(() => asComponentId("component_too_short")).toThrow();
    expect(tryAsComponentId("component_too_short")).toBeNull();
    expect(tryAsSetupId("setup_too_short")).toBeNull();
    expect(tryAsAccountId("not-an-id")).toBeNull();
    expect(tryAsComponentId("component_01JQZK7B8N4M6P2R9T5V0X3Y7Z")).toBe(
      "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
    );
  });
});
