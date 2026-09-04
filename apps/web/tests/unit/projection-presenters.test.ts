import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { machineDocumentToText } from "@/lib/projection/document-text";
import { componentPublicFacts } from "@/lib/projection/page-facts";
import {
  presentCatalog,
  presentComponentDetail,
  presentDocs,
  presentLanding,
  presentPlatformContext,
} from "@/lib/projection/presenters";
import {
  presentCountry,
  presentService,
  presentServicesIndex,
} from "@/lib/projection/regional-presenters";
import { pairedPath, projectedHref } from "@/lib/projection/paths";
import { GET as llmsFull } from "@/app/llms-full.txt/route";
import { resetEnvCache } from "@/lib/env";

const PRESENTER_PATHS = [
  "/",
  "/catalog",
  "/catalog/components/cmp_demo",
  "/catalog/setups/stp_demo",
  "/catalog/components/cmp_demo/versions/1.0",
  "/catalog/setups/stp_demo/versions/1.0",
  "/publishers/acc_demo",
  "/docs",
  "/docs/guide",
  "/legal/privacy",
  "/services",
  "/services/example.test",
  "/countries/KZ",
] as const;

const PRIVATE_PATHS = ["/account", "/devices", "/objects", "/access", "/reports"] as const;

describe("machine presenters (REQ-3609, REQ-3610, REQ-3608)", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_APP_URL", "http://localhost:3000");
    vi.stubEnv("AI_STP_API_BASE_URL", "http://localhost:8000");
    vi.stubEnv("AI_STP_SESSION_SECRET", "dev-only-change-me-to-a-long-random-string");
    vi.stubEnv("AI_STP_USER_DOCS_URL", "http://localhost:8011");
    vi.stubEnv("AI_STP_USE_MOCKS", "true");
    resetEnvCache();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("keeps every route addressable in the machine projection", () => {
    // Navigation must never drop the reader back into the human site, and no
    // route loses its machine representation (REQ-3609, REQ-3611).
    for (const path of [...PRESENTER_PATHS, ...PRIVATE_PATHS, "/contact", "/login"]) {
      expect(projectedHref(path, "en"), path).toMatch(/^\/en\/ai(\/|$)/);
    }
  });

  it("builds object documents with required technical fields and no media", () => {
    const doc = presentComponentDetail({
      facts: componentPublicFacts(
        {
          stable_id: "cmp_x",
          publisher_id: "acc_y",
          latest_name: "Demo",
          latest_description: "A component",
          latest_version: "1.2",
          latest_harness_id: "claude-code",
          latest_component_type: "skill",
          latest_lifecycle: "published",
          latest_tags: ["ops"],
          latest_trust: {
            trust_lane: "authoritative",
            author_verified: true,
            component_verified: false,
          },
        },
        "sha256:abc",
      ),
      labels: {
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
      },
    });
    const text = machineDocumentToText(doc, "en");
    expect(text).toContain("stable_id: cmp_x");
    expect(text).toContain("version: 1.2");
    expect(text).toContain("digest: sha256:abc");
    expect(text).toContain("harness: claude-code");
    expect(text).toContain("trust_lane: authoritative");
    expect(text).toContain("author_verified: Yes");
    expect(text).toContain("component_verified: No");
    expect(text).toContain("ai-stp registry version --kind component --id cmp_x --version 1.2");
    expect(text).not.toMatch(/<img|image\/|avatar/i);
  });

  it("shares presenters with llms-full.txt", async () => {
    const body = await (await llmsFull()).text();
    const platform = machineDocumentToText(presentPlatformContext(), "en");
    const landing = machineDocumentToText(
      presentLanding({
        title: "The AI setup registry, not just a skill catalog",
        subtitle: "Find, verify, install, and earn on AI components.",
        browseCatalog: "Browse catalog",
        installCommand: "uv tool install ai-stp-cli",
        installHeading: "Install the CLI",
      }),
      "en",
    );
    expect(body).toContain("local_owner_or_pinned");
    expect(body).toContain(platform.trim().slice(0, 40));
    expect(body).toContain(landing.trim().slice(0, 40));
  });

  it("presents country and service facts without media", () => {
    const country = machineDocumentToText(
      presentCountry({
        title: "Kazakhstan",
        code: "KZ",
        services: [{ name: "Kaspi", domain: "kaspi.kz" }],
        objects: [{ name: "planner" }],
      }),
      "en",
    );
    expect(country).toContain("[Kaspi](/en/ai/services/kaspi.kz)");
    expect(country).toContain("code: KZ");
    expect(country).not.toMatch(/<img|avatar/i);

    const service = machineDocumentToText(
      presentService({
        name: "Kaspi",
        domain: "kaspi.kz",
        primaryUrl: "https://kaspi.kz",
        countryCodes: ["KZ"],
        objects: [{ name: "planner", kind: "component", stableId: "component_01H" }],
      }),
      "en",
    );
    expect(service).toContain("[KZ](/en/ai/countries/KZ)");
    expect(service).toContain("https://kaspi.kz");

    const index = machineDocumentToText(
      presentServicesIndex({
        title: "Services",
        subtitle: "CIS",
        emptyMessage: "None",
        services: [{ name: "Kaspi", domain: "kaspi.kz" }],
      }),
      "en",
    );
    expect(index).toContain("[Kaspi](/en/ai/services/kaspi.kz)");
  });

  it("keeps catalog query fields in the machine document (REQ-3624)", () => {
    const text = machineDocumentToText(
      presentCatalog({
        title: "Catalog",
        subtitle: "Browse",
        components: [],
        setups: [],
        labels: {
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
        },
        queryFields: [
          ["q", "hook"],
          ["component_type", "hook"],
        ],
        emptyMessage: "None",
      }),
      "en",
    );
    expect(text).toContain("q: hook");
    expect(text).toContain("component_type: hook");
  });

  it("nests documentation pages under section headings", () => {
    const text = machineDocumentToText(
      presentDocs({
        title: "Overview",
        description: "Help center",
        bodyText: "Body",
        nav: [
          { title: "Overview", href: "/docs" },
          {
            title: "Quickstart",
            href: "/docs/quickstart",
            children: [
              { title: "For people", href: "/docs/quickstart/human" },
              { title: "For agents", href: "/docs/quickstart/agent" },
            ],
          },
        ],
      }),
      "en",
    );
    expect(text).toContain("### Quickstart");
    expect(text).toContain("[Quickstart](/en/ai/docs/quickstart)");
    expect(text).toContain("[For agents](/en/ai/docs/quickstart/agent)");
  });

  it("builds machine paired paths", () => {
    expect(pairedPath("/catalog", "machine", "en")).toBe("/en/ai/catalog");
    expect(pairedPath("/en/ai/catalog", "human", "en")).toBe("/en/catalog");
    expect(pairedPath("/", "machine", "ru")).toBe("/ru/ai");
    expect(pairedPath("https://docs.example.test", "machine", "ru")).toBe(
      "https://docs.example.test",
    );
  });
});
