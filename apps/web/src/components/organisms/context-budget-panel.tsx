import { DetailAccordion } from "@/components/molecules/detail-accordion";
import {
  contextBudgetMessage,
  type ContextBudgetLabels,
} from "@/components/organisms/context-budget-labels";
import type { ComponentContextBudget, SetupContextBudget } from "@/lib/api/catalog";
import { UI } from "@/lib/ui-selectors";

export type { ContextBudgetLabels } from "@/components/organisms/context-budget-labels";
export { contextBudgetLabels } from "@/components/organisms/context-budget-labels";

export function ContextBudgetPanel({
  budget,
  labels,
  failure,
}: {
  budget: SetupContextBudget | null;
  labels: ContextBudgetLabels;
  failure?: string | null;
}) {
  const ready = budget !== null && budget.status === "ready";
  const unavailable = contextBudgetMessage(
    labels,
    budget?.status === "invalid_graph" ? "invalid_graph" : (budget?.reason ?? failure),
  );
  const summary = ready ? `${budget.total_tokens} ${labels.tokens}` : unavailable;

  return (
    <div data-ui={UI.component.contextBudget}>
      <DetailAccordion title={labels.title} summary={summary}>
        {ready ? (
          <div>
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-muted-foreground">{labels.total}</dt>
                <dd className="mt-1 text-xl font-medium tabular-nums">
                  {budget.total_tokens.toLocaleString()}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">{labels.conditional}</dt>
                <dd className="mt-1 text-xl font-medium tabular-nums">
                  {budget.conditional_tokens.toLocaleString()}
                </dd>
              </div>
            </dl>
            {budget.unavailable_components > 0 ? (
              <p className="text-muted-foreground mt-4 text-sm" role="status">
                {labels.unavailable}: {budget.unavailable_components}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="text-sm" role="status">
            {unavailable}
          </p>
        )}
      </DetailAccordion>
      <p className="text-muted-foreground mt-2 text-xs">{labels.lead}</p>
    </div>
  );
}

export function ComponentContextBudgetPanel({
  budget,
  labels,
  failure,
}: {
  budget: ComponentContextBudget | null;
  labels: ContextBudgetLabels;
  failure?: string | null;
}) {
  const tokens = budget?.tokens;
  const runtimeDerived = labels.runtimeDerived ?? labels.error;
  const measured =
    (budget?.status === "exact" || budget?.status === "estimated") && typeof tokens === "number";
  const unavailable = contextBudgetMessage(labels, budget?.reason ?? failure);
  const summary = measured
    ? `${tokens.toLocaleString()} ${labels.tokens}`
    : budget?.status === "not_applicable"
      ? runtimeDerived
      : unavailable;
  return (
    <div data-ui={UI.component.contextBudget}>
      <DetailAccordion title={labels.title} summary={summary}>
        {measured ? (
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-muted-foreground">{labels.total}</dt>
              <dd className="mt-1 text-xl font-medium tabular-nums">{tokens.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">{labels.conditional}</dt>
              <dd className="mt-1 text-xl font-medium tabular-nums">
                {(budget?.loading === "conditional" ? tokens : 0).toLocaleString()}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-muted-foreground text-sm" role="status">
            {budget?.status === "not_applicable" ? runtimeDerived : unavailable}
          </p>
        )}
      </DetailAccordion>
      <p className="text-muted-foreground mt-2 text-xs">{labels.componentLead ?? labels.lead}</p>
    </div>
  );
}
