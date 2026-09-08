import type {
  ComponentSummary,
  OwnerObjectSummary,
  SetupSummary,
} from "@/lib/api/generated/types.gen";
import type { ParsedCatalogQuery } from "@/lib/catalog-query";

type OwnerCatalogItem = ComponentSummary | SetupSummary;

export function ownerCatalogItem(item: OwnerObjectSummary): OwnerCatalogItem | null {
  const value = item.catalog_item;
  return value && "latest_name" in value ? value : null;
}

export function filterAndSortOwnerObjects(
  items: readonly OwnerObjectSummary[],
  query: ParsedCatalogQuery,
): OwnerObjectSummary[] {
  const filtered = items.filter((item) => matchesOwnerQuery(item, query));
  const direction = query.sortDirection === "asc" ? 1 : -1;
  return filtered
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const a = ownerCatalogItem(left.item);
      const b = ownerCatalogItem(right.item);
      const primary =
        query.sort === "likes"
          ? (a?.likes_count ?? 0) - (b?.likes_count ?? 0)
          : query.sort === "updated_at"
            ? left.item.updated_at.localeCompare(right.item.updated_at)
            : 0;
      return primary * direction || left.index - right.index;
    })
    .map(({ item }) => item);
}

// Keep the owner workspace on the same filter contract as the catalog.
// eslint-disable-next-line complexity
function matchesOwnerQuery(item: OwnerObjectSummary, query: ParsedCatalogQuery): boolean {
  const card = ownerCatalogItem(item);
  if (query.resource !== "all" && item.object_kind !== query.resource.slice(0, -1)) return false;
  const text = [
    item.name,
    item.stable_id,
    card && "latest_description" in card ? card.latest_description : "",
    card && "publisher_id" in card ? card.publisher_id : "",
    ...(card?.latest_tags ?? []),
  ]
    .join(" ")
    .toLocaleLowerCase();
  if (query.q && !text.includes(query.q.toLocaleLowerCase())) return false;
  if (query.tags.some((tag) => !card?.latest_tags.includes(tag))) return false;
  const harnessIds = query.harnessIds.length
    ? query.harnessIds
    : query.harnessId
      ? [query.harnessId]
      : [];
  if (
    harnessIds.length &&
    !harnessIds.some((id) => card?.latest_harness_ids.some((value) => value === id))
  ) {
    return false;
  }
  const component = card && isComponentSummary(card) ? card : null;
  const componentTypes = query.componentTypes.length
    ? query.componentTypes
    : query.componentType
      ? [query.componentType]
      : [];
  if (
    componentTypes.length &&
    (!component || !componentTypes.includes(component.latest_component_type))
  ) {
    return false;
  }
  if (query.authors.length && (!card || !query.authors.includes(card.publisher_id))) return false;
  const verified = Boolean(
    card?.latest_trust.author_verified && card.latest_trust.component_verified,
  );
  if (query.verifiedOnly && !verified) return false;
  if (
    query.verification.length &&
    !query.verification.includes(verified ? "verified" : "not_verified")
  ) {
    return false;
  }
  if (
    query.minSafetyPercent !== undefined &&
    (!component?.latest_checks ||
      (component.latest_checks.checks_passed_percent ?? -1) < query.minSafetyPercent)
  ) {
    return false;
  }
  if (query.supportTier && card?.latest_support.tier !== query.supportTier) return false;
  if (query.supportState && card?.latest_support.state !== query.supportState) return false;
  if (query.updatedFrom && item.updated_at.slice(0, 10) < query.updatedFrom) return false;
  if (query.updatedTo && item.updated_at.slice(0, 10) > query.updatedTo) return false;
  if (!query.includeExperimental && !verified) return false;
  return true;
}

function isComponentSummary(item: OwnerCatalogItem): item is ComponentSummary {
  return "latest_component_type" in item;
}
