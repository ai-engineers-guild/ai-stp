import {
  CorporateRelationSection,
  type CorporateRelationSectionLabels,
} from "@/components/organisms/corporate-relation-section";
import type { DirectoryResource } from "@/components/organisms/corporate-directory-types";
import type { CorporateCatalogUsage as CorporateCatalogUsageItem } from "@/lib/api/generated/types.gen";

const SUBJECT_RESOURCES = {
  employee: "members",
  team: "teams",
  project: "projects",
  technology: "technologies",
} as const satisfies Record<CorporateCatalogUsageItem["subject_kind"], DirectoryResource>;

export function CorporateCatalogUsage({
  items,
  total,
  labels,
}: {
  items: CorporateCatalogUsageItem[];
  /** Authorized usage rows the server counted, including rows this page did not fetch. */
  total: number;
  labels: {
    subjectSections: Record<CorporateCatalogUsageItem["subject_kind"], string>;
    relation: CorporateRelationSectionLabels;
    truncated: string;
  };
}) {
  const truncated = items.length < total;
  return (
    <>
      {(Object.keys(SUBJECT_RESOURCES) as (keyof typeof SUBJECT_RESOURCES)[]).map((kind) => {
        const resource = SUBJECT_RESOURCES[kind];
        const references = [
          ...new Map(
            items
              .filter((item) => item.subject_kind === kind)
              .map((item) => [item.subject_id, { id: item.subject_id, name: item.subject_name }]),
          ).values(),
        ];
        return (
          <CorporateRelationSection
            key={kind}
            title={labels.subjectSections[kind]}
            resource={resource}
            references={references}
            api={{ resource, subjectIds: references.map((reference) => reference.id) }}
            labels={labels.relation}
          />
        );
      })}
      {truncated ? (
        <p className="text-muted-foreground text-sm">
          {labels.truncated
            .replace("{shown}", String(items.length))
            .replace("{total}", String(total))}
        </p>
      ) : null}
    </>
  );
}
