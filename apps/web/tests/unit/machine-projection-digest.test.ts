import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/catalog", async () => {
  const fixtures = await import("@/mocks/fixtures/catalog");
  return {
    readComponent: () => Promise.resolve(fixtures.componentDetail),
    readSetup: () => Promise.resolve(fixtures.setupDetail),
    catalogRelations: () => ({ country_codes: [], services: [] }),
    readComponentVersion: () => Promise.reject(new Error("not used here")),
    readSetupVersion: () => Promise.reject(new Error("not used here")),
    listExternalProducts: () => Promise.resolve({ items: [] }),
    searchComponents: () => Promise.resolve({ items: [], experimental: [] }),
    searchSetups: () => Promise.resolve({ items: [], experimental: [] }),
  };
});

// The resolver reads its labels through next-intl; the subject here is which
// digest it pairs with which version, so translation is stubbed to identity.
vi.mock("next-intl/server", () => ({
  getTranslations: () => Promise.resolve((key: string) => key),
}));

const { componentDetail, setupDetail } = await import("@/mocks/fixtures/catalog");
const { resolveMachineDocument } = await import("@/lib/projection/registry");
const { machineDocumentToText } = await import("@/lib/projection/document-text");

async function machineText(segments: string[]): Promise<string> {
  const document = await resolveMachineDocument({ segments, locale: "en", searchParams: {} });
  if (document === null) {
    throw new Error(`no machine route for ${segments.join("/")}`);
  }
  return machineDocumentToText(document, "en");
}

function digestOf(
  versions: readonly { version: string; passport_digest: string }[],
  version: string,
): string {
  const row = versions.find((candidate) => candidate.version === version);
  if (row === undefined) {
    throw new Error(`fixture has no version ${version}`);
  }
  return row.passport_digest;
}

describe("machine projection pairs a version with its own digest", () => {
  it("shows the digest of the version it names, not of the oldest row", async () => {
    // The API returns versions ascending, so the first row is the oldest while
    // the heading is built from `latest_version`. Pairing them printed `1.2`
    // beside the digest of `1.0` — precise and wrong, on the surface an agent
    // reads and pins from.
    const rows = componentDetail.versions;
    const latest = componentDetail.summary.latest_version;
    expect(rows.length).toBeGreaterThan(1);

    const oldest = rows[0];
    if (oldest === undefined) {
      throw new Error("fixture lists no versions");
    }
    expect(oldest.version).not.toBe(latest);

    const expected = digestOf(rows, latest);
    expect(expected).not.toBe(oldest.passport_digest);

    const text = await machineText(["catalog", "components", componentDetail.summary.stable_id]);
    expect(text).toContain(expected);
    expect(text).not.toContain(oldest.passport_digest);
  });

  it("does the same for setups", async () => {
    // The same controls as the component case, and their absence is why this
    // half could not fail: the setup fixture carried a single version, so
    // `versions[0]` and the row named by `latest_version` were the same object
    // and `toContain` passed either way. Production shipped a setup page
    // naming 1.1 beside 1.0's digest, and `evidence-live` caught it against the
    // deployed site rather than here.
    const rows = setupDetail.versions;
    const latest = setupDetail.summary.latest_version;
    expect(rows.length).toBeGreaterThan(1);

    const oldest = rows[0];
    if (oldest === undefined) {
      throw new Error("fixture lists no versions");
    }
    expect(oldest.version).not.toBe(latest);

    const expected = digestOf(rows, latest);
    expect(expected).not.toBe(oldest.passport_digest);

    const text = await machineText(["catalog", "setups", setupDetail.summary.stable_id]);
    expect(text).toContain(expected);
    expect(text).not.toContain(oldest.passport_digest);
  });
});
