import { describe, expect, it } from "vitest";

import { browserDeviceLabel } from "@/lib/device-label";

describe("browserDeviceLabel", () => {
  it("distinguishes common browser and device families", () => {
    expect(
      browserDeviceLabel(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
      ),
    ).toBe("Edge 140.0.0.0 · Windows");
    expect(
      browserDeviceLabel(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.6 Mobile/15E148 Safari/604.1",
      ),
    ).toBe("Safari 18.6 · iPhone");
    expect(browserDeviceLabel(null)).toBeNull();
  });
});
