"use client";

import { useTechnologyReview } from "@/lib/technology-review-state";
import {
  TechnologyReviewHeader,
  TechnologyScanMetadata,
  TechnologyReviewFilters,
} from "./technology-review-header";
import { TechnologyFindingsTable } from "./technology-findings-table";
import { TechnologyReviewDialogs } from "./technology-review-dialogs";

export function TechnologyScanFindings(props: Parameters<typeof useTechnologyReview>[0]) {
  const state = useTechnologyReview(props);
  return (
    <div aria-busy={state.mutation.busy} className="space-y-3">
      <TechnologyReviewHeader state={state} />
      <TechnologyScanMetadata state={state} />
      <TechnologyReviewFilters state={state} />
      {state.mutation.message && (
        <p role="status" className="text-sm">
          {state.mutation.message}
        </p>
      )}
      <TechnologyFindingsTable state={state} />
      <TechnologyReviewDialogs state={state} />
    </div>
  );
}
