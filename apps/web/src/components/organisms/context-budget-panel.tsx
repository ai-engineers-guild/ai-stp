import { DetailAccordion } from "@/components/molecules/detail-accordion";
import type { ContextBudgetLabels } from "@/components/organisms/context-budget-labels";
import type { ComponentContextBudget, SetupContextBudget } from "@/lib/api/catalog";
import { UI } from "@/lib/ui-selectors";

export type { ContextBudgetLabels } from "@/components/organisms/context-budget-labels";
export { contextBudgetLabels } from "@/components/organisms/context-budget-labels";

export function ContextBudgetPanel({
  budget,
  labels,
}: {
  budget: SetupContextBudget | null;
  labels: ContextBudgetLabels;
}) {
  const ready = budget !== null && budget.status !== "invalid_graph";
  const summary = ready ? `${budget.total_tokens} ${labels.tokens}` : labels.error;

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
            {labels.error}
          </p>
        )}
      </DetailAccordion>
    </div>
  );
}

export function ComponentContextBudgetPanel({
  budget,
  labels,
}: {
  budget: ComponentContextBudget | null;
  labels: ContextBudgetLabels;
}) {
  const tokens = budget?.tokens;
  const runtimeDerived = labels.runtimeDerived ?? labels.error;
  const measured = typeof tokens === "number";
  const summary = measured
    ? `${tokens.toLocaleString()} ${labels.tokens}`
    : budget?.status === "not_applicable"
      ? runtimeDerived
      : labels.error;
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
            {budget?.status === "not_applicable" ? runtimeDerived : labels.error}
          </p>
        )}
      </DetailAccordion>
    </div>
  );
}
