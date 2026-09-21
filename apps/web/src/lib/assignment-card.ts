import type { CorporateCatalogAssignment } from "@/lib/api/generated/types.gen";
import type { OwnerCardItem } from "@/components/organisms/object-card";

export function assignmentCardItem(item: CorporateCatalogAssignment): OwnerCardItem {
  return {
    schema_version: 1,
    author_verified: false,
    component_verified: false,
    catalog_item: null,
    latest_version: item.version,
    lifecycle_state: "active",
    name: item.display_name ?? item.stable_id,
    object_kind: item.object_kind,
    stable_id: item.stable_id,
    trust_lane: null,
    updated_at: "1970-01-01T00:00:00Z",
  };
}
