"use client";
import type {
  useGovernanceMutation,
  GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import type { TechnologyView } from "@/lib/api/generated/types.gen";
import { displayCategoryIds } from "@/lib/technology-taxonomy";
import type { Draft, Row } from "@/lib/technology-review-state";

export function defaultDraft(row: Row, names: Map<string, TechnologyView>): Draft {
  const technology = row.technology_id ?? row.candidate_technology_id ?? "";
  const record = names.get(technology);
  return {
    technology,
    category: row.category_id ?? (record ? (displayCategoryIds(record)[0] ?? "") : ""),
    comment: row.comment,
    review:
      row.state === "rejected" ? "rejected" : row.review === "confirmed" ? "confirmed" : "open",
  };
}

export function canApplyFinding(draft: Draft, names: Map<string, TechnologyView>) {
  return (
    draft.review === "rejected" ||
    draft.review === "dependency" ||
    ((draft.technology || draft.category) && names.get(draft.technology)?.lifecycle !== "archived")
  );
}

function findingDecision(row: Row, value: Draft) {
  return {
    scan_id: row.scan.scan_id,
    kind: row.kind,
    coordinate: row.coordinate,
    context: row.context,
    technology_id: value.technology || null,
    category_id: value.category || null,
    review: value.review === "open" ? "confirmed" : value.review,
    expected_revision: row.review_revision,
    comment: value.comment,
  };
}

export function applyFindings(
  mutation: ReturnType<typeof useGovernanceMutation>,
  authority: GovernanceAuthority,
  items: Row[],
  decide: (row: Row) => Draft,
  onSaved: () => void,
) {
  const decisions = items.flatMap((row) =>
    (row.members ?? [row]).map((member) => findingDecision(member, decide(row))),
  );
  mutation.save(
    `/v1/corporate/organizations/${authority.organizationId}/technology-findings/review`,
    { expected_revision: 0, items: decisions },
    "PUT",
    onSaved,
  );
}
