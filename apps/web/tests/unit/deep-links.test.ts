import { describe, expect, it } from "vitest";

import { DEEP_LINK_CORPUS } from "@/lib/generated/deep-link-corpus";
import {
  DeepLinkError,
  buildDeepLink,
  normalizeTarget,
  parseDeepLink,
  type DeepLinkTarget,
} from "@/lib/deep-links";

function asTarget(raw: Record<string, unknown>): DeepLinkTarget {
  return normalizeTarget({
    kind: raw["kind"] as DeepLinkTarget["kind"],
    stable_id: String(raw["stable_id"]),
    ...(typeof raw["version"] === "string" ? { version: raw["version"] } : {}),
    ...(raw["locale"] === "en" || raw["locale"] === "ru" ? { locale: raw["locale"] } : {}),
    ...(raw["intent"] === "report" ? { intent: "report" } : {}),
  });
}

describe("deep-link corpus", () => {
  it("round-trips every positive case", () => {
    for (const item of DEEP_LINK_CORPUS.positive) {
      const target = asTarget(item.target);
      const view = buildDeepLink(item.platform_base, target);
      expect(view.web_url).toBe(item.web_url);
      expect(view.cli_argv).toEqual([...item.cli_argv]);
      expect(parseDeepLink(item.platform_base, view.web_url)).toEqual(target);
    }
  });

  it("rejects invalid targets", () => {
    for (const raw of DEEP_LINK_CORPUS.invalid_targets) {
      expect(() => asTarget(raw as Record<string, unknown>)).toThrow(DeepLinkError);
    }
  });

  it("rejects hostile URLs against the example origin", () => {
    for (const webUrl of DEEP_LINK_CORPUS.invalid_urls) {
      expect(() => parseDeepLink("https://example.test", webUrl)).toThrow(DeepLinkError);
    }
  });
});
