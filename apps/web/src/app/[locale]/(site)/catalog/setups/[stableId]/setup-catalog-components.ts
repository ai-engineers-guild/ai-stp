import { readComponentVersion } from "@/lib/api/catalog";
import type { SetupVersionPassport } from "@/lib/api/generated/types.gen";
import { readPublisherProfile, type PublicProfileProjection } from "@/lib/api/public-profile";
import { asAccountId, asComponentId, asVersionId } from "@/lib/brands";
import { sourceLinksFor } from "@/lib/source-url";

export async function readAuthor(accountId: string): Promise<PublicProfileProjection | null> {
  try {
    return await readPublisherProfile(asAccountId(accountId));
  } catch {
    return null;
  }
}

export async function loadCatalogComponents(passport: SetupVersionPassport, publisherId: string) {
  const items = await Promise.all(
    passport.components.map(async (ref) => {
      try {
        const component = await readComponentVersion(
          asComponentId(ref.stable_id),
          asVersionId(ref.version),
        );
        const ownerId = publisherId || component.passport.owner_id || "";
        const author = await readAuthor(ownerId);
        return {
          stableId: ref.stable_id,
          version: ref.version,
          componentType: component.passport.component_type,
          ownerId,
          authorName: author?.display_name,
          sourceUrl: sourceLinksFor(component.passport.source, component.passport.facts)[0]?.href,
          passport: component.passport,
        };
      } catch {
        return null;
      }
    }),
  );
  return items.filter((item) => item !== null);
}
