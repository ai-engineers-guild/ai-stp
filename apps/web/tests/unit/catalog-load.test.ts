import { describe, expect, it, vi } from "vitest";

import type { AccountId } from "@/lib/brands";
import {
  loadPublisherProfiles,
  startCatalogResourceReads,
  type CatalogReadDeps,
} from "@/lib/catalog-load";
import { defaultCatalogQuery } from "@/lib/catalog-query-defaults";
import {
  FIXTURE_ACCOUNT_ID,
  SEED_AUTHOR_NORTHWIND_ID,
  SEED_AUTHOR_RIVER_ID,
} from "@/mocks/fixtures/identity";

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const emptyList = {
  schema_version: 1 as const,
  items: [],
  experimental: [],
  page: { schema_version: 1 as const, next_cursor: null, page_size: 25 },
};

describe("catalog resource orchestration", () => {
  it("starts services, components, and setups before any of them resolve", async () => {
    const started: string[] = [];
    const services = deferred<{ schema_version: 1; items: never[] }>();
    const components = deferred<typeof emptyList>();
    const setups = deferred<typeof emptyList>();
    const deps: CatalogReadDeps = {
      listExternalProducts: () => {
        started.push("services");
        return services.promise;
      },
      searchComponents: () => {
        started.push("components");
        return components.promise;
      },
      searchSetups: () => {
        started.push("setups");
        return setups.promise;
      },
    };

    const reads = startCatalogResourceReads(defaultCatalogQuery("all"), deps);
    expect(started).toEqual(["services", "components", "setups"]);

    services.resolve({ schema_version: 1, items: [] });
    components.resolve(emptyList);
    setups.resolve(emptyList);
    await expect(
      Promise.all([reads.services, reads.components, reads.setups]),
    ).resolves.toHaveLength(3);
  });

  it("starts only the requested resource plus services", () => {
    const started: string[] = [];
    const deps: CatalogReadDeps = {
      listExternalProducts: () => {
        started.push("services");
        return Promise.resolve({ schema_version: 1, items: [] });
      },
      searchComponents: () => {
        started.push("components");
        return Promise.resolve(emptyList);
      },
      searchSetups: () => {
        started.push("setups");
        return Promise.resolve(emptyList);
      },
    };
    startCatalogResourceReads(defaultCatalogQuery("components"), deps);
    expect(started).toEqual(["services", "components"]);
  });

  it("keeps a services failure as an empty list without inventing search success", async () => {
    const deps: CatalogReadDeps = {
      listExternalProducts: () => Promise.reject(new Error("services down")),
      searchComponents: () => Promise.reject(new Error("search down")),
      searchSetups: () => Promise.resolve(emptyList),
    };
    const reads = startCatalogResourceReads(defaultCatalogQuery("all"), deps);
    await expect(reads.services).resolves.toEqual([]);
    await expect(reads.components).rejects.toThrow("search down");
  });
});

describe("publisher profile fan-out", () => {
  it("deduplicates ids, bounds concurrency, and isolates per-id failures", async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    const seen: string[] = [];
    const readProfile = vi.fn(async (accountId: AccountId) => {
      seen.push(accountId);
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await Promise.resolve();
      inFlight -= 1;
      if (accountId === SEED_AUTHOR_RIVER_ID) {
        throw new Error("profile unavailable");
      }
      return { display_name: accountId, avatar_url: null };
    });

    const profiles = await loadPublisherProfiles(
      [
        FIXTURE_ACCOUNT_ID,
        SEED_AUTHOR_NORTHWIND_ID,
        FIXTURE_ACCOUNT_ID,
        SEED_AUTHOR_RIVER_ID,
        SEED_AUTHOR_NORTHWIND_ID,
      ],
      readProfile,
      2,
    );

    expect(readProfile).toHaveBeenCalledTimes(3);
    expect(seen.sort()).toEqual(
      [FIXTURE_ACCOUNT_ID, SEED_AUTHOR_NORTHWIND_ID, SEED_AUTHOR_RIVER_ID].sort(),
    );
    expect(maxInFlight).toBeLessThanOrEqual(2);
    expect(profiles[FIXTURE_ACCOUNT_ID]).toEqual({
      displayName: FIXTURE_ACCOUNT_ID,
      avatarUrl: null,
    });
    expect(profiles[SEED_AUTHOR_RIVER_ID]).toEqual({ displayName: null, avatarUrl: null });
  });
});
