import { describe, expect, it } from "vitest";

import { spdxLicenseUrl } from "@/lib/spdx-license";

describe("spdxLicenseUrl", () => {
  it("maps known SPDX identifiers to official pages", () => {
    expect(spdxLicenseUrl("MIT")).toBe("https://spdx.org/licenses/MIT.html");
    expect(spdxLicenseUrl("AGPL-3.0-or-later")).toBe(
      "https://spdx.org/licenses/AGPL-3.0-or-later.html",
    );
  });

  it("does not invent a URL for an unknown identifier", () => {
    expect(spdxLicenseUrl("Proprietary-Custom")).toBeNull();
    expect(spdxLicenseUrl("MIT OR Apache-2.0")).toBeNull();
    expect(spdxLicenseUrl("")).toBeNull();
  });
});
