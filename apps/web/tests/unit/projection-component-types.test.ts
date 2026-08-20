import { describe, expect, it } from "vitest";

import { machineDocumentToText } from "@/lib/projection/document-text";
import { COMPONENT_TYPES } from "@/lib/projection/inventory";
import {
  componentPublicFacts,
  machineTextLeaks,
  type ComponentSummaryFacts,
} from "@/lib/projection/page-facts";
import { presentCatalog, presentComponentDetail } from "@/lib/projection/presenters";

const LABELS = {
  yes: "Yes",
  no: "No",
  stableId: "stable_id",
  version: "version",
  digest: "digest",
  harness: "harness",
  trustLane: "trust_lane",
  authorVerified: "author_verified",
  componentVerified: "component_verified",
  install: "install",
  type: "type",
};

function summary(type: string): ComponentSummaryFacts {
  return {
    stable_id: `component_${type}`,
    publisher_id: "account_01H",
    latest_name: `${type}-demo`,
    latest_description: `A ${type} component`,
    latest_version: "1.0",
    latest_harness_id: "claude-code",
    latest_component_type: type,
    latest_lifecycle: "published",
    latest_tags: ["ops"],
    latest_trust: {
      trust_lane: "authoritative",
      author_verified: true,
      component_verified: false,
    },
  };
}

describe("machine documents for every component type (REQ-3621, REQ-3625)", () => {
  it.each(COMPONENT_TYPES)("builds a complete object document for %s", (type) => {
    const facts = componentPublicFacts(summary(type), "sha256:abc");
    expect(facts.componentType).toBe(type);
    const text = machineDocumentToText(
      presentComponentDetail({
        facts,
        labels: LABELS,
      }),
      "en",
    );
    expect(text).toContain(`type: ${type}`);
    expect(text).toContain("stable_id: component_" + type);
    expect(text).toContain("version: 1.0");
    expect(text).toContain("digest: sha256:abc");
    expect(text).toContain("harness: claude-code");
    expect(text).toContain("trust_lane: authoritative");
    expect(text).toContain("author_verified: Yes");
    expect(text).toContain("component_verified: No");
    expect(text).toContain("](");
    expect(machineTextLeaks(text)).toBe(false);
    expect(text).not.toMatch(/<img|avatar|csrf|session_token|operation_id/i);
  });

  it("lists component type on the catalog document", () => {
    const doc = presentCatalog({
      title: "Catalog",
      subtitle: "Browse",
      components: COMPONENT_TYPES.map((type) => ({
        ...summary(type),
        latest_published_at: "2026-01-01",
        likes_count: 0,
      })),
      setups: [],
      labels: LABELS,
      queryFields: [["component_type", "skill"]],
    });
    const text = machineDocumentToText(doc, "en");
    for (const type of COMPONENT_TYPES) {
      expect(text).toContain(`type: ${type}`);
    }
    expect(text).toContain("component_type: skill");
  });
});
