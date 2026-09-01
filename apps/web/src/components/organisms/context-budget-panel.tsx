import { DetailAccordion } from "@/components/molecules/detail-accordion";
import type { ContextBudgetLabels } from "@/components/organisms/context-budget-labels";
import { ContextBudgetLocalCheck } from "@/components/organisms/context-budget-local-check";
import { ContextCostCalculator } from "@/components/organisms/context-cost-calculator";
import type { ComponentContextBudget, SetupContextBudget } from "@/lib/api/catalog";
import { UI } from "@/lib/ui-selectors";

export type { ContextBudgetLabels } from "@/components/organisms/context-budget-labels";
export { contextBudgetLabels } from "@/components/organisms/context-budget-labels";

function loadingLabel(loading: "always" | "conditional", labels: ContextBudgetLabels): string {
  return loading === "always" ? labels.always : labels.conditional;
}

export function ContextBudgetPanel({
  budget,
  command,
  labels,
}: {
  budget: SetupContextBudget | null;
  command: string;
  labels: ContextBudgetLabels;
}) {
  const ready = budget !== null && budget.status !== "invalid_graph";
  const summary = ready ? `${labels.lead} ${budget.total_tokens} ${labels.tokens}` : labels.error;

  return (
    <div data-ui={UI.component.contextBudget}>
      <DetailAccordion title={labels.title} summary={summary}>
        {ready ? (
          <div className="space-y-4">
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-muted-foreground">{labels.always}</dt>
                <dd className="font-mono tabular-nums">{budget.always_tokens}</dd>
                <p className="text-muted-foreground text-xs">{labels.alwaysHint}</p>
              </div>
              <div>
                <dt className="text-muted-foreground">{labels.conditional}</dt>
                <dd className="font-mono tabular-nums">{budget.conditional_tokens}</dd>
                <p className="text-muted-foreground text-xs">{labels.conditionalHint}</p>
              </div>
              <div>
                <dt className="text-muted-foreground">{labels.total}</dt>
                <dd className="font-mono tabular-nums">{budget.total_tokens}</dd>
              </div>
            </dl>
            {budget.unavailable_components > 0 ? (
              <p className="text-sm" role="status">
                {labels.unavailable}: {budget.unavailable_components}
              </p>
            ) : null}
            {budget.components.length === 0 ? (
              <p className="text-sm">{labels.empty}</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {budget.components.map((item) => (
                  <li key={`${item.component.stable_id}@${item.component.version}`}>
                    <span className="font-mono text-xs">
                      {item.component.stable_id}@{item.component.version}
                    </span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {loadingLabel(item.loading, labels)} ·{" "}
                      {item.tokens === null ? item.status : `${item.tokens} ${labels.tokens}`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <ContextCostCalculator totalTokens={budget.total_tokens} labels={labels.cost} />
            <ContextBudgetLocalCheck command={command} labels={labels} />
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
  const componentLead = labels.componentLead ?? labels.lead;
  const runtimeDerived = labels.runtimeDerived ?? labels.error;
  const measured = typeof tokens === "number";
  const summary = measured
    ? `${componentLead} ${tokens} ${labels.tokens}`
    : budget?.status === "not_applicable"
      ? runtimeDerived
      : labels.error;
  return (
    <div data-ui={UI.component.contextBudget}>
      <DetailAccordion title={labels.title} summary={summary}>
        {measured ? (
          <div className="space-y-4">
            <p className="text-muted-foreground text-sm">{componentLead}</p>
            <p className="font-mono text-2xl font-medium tabular-nums">
              {tokens} <span className="text-base">{labels.tokens}</span>
            </p>
            <p className="text-muted-foreground text-sm">
              {budget?.loading === "always" ? labels.alwaysHint : labels.conditionalHint}
            </p>
            <ContextCostCalculator totalTokens={tokens} labels={labels.cost} />
          </div>
        ) : (
          <p className="text-muted-foreground text-sm" role="status">
            {budget?.status === "not_applicable" ? runtimeDerived : labels.error}
          </p>
        )}
      </DetailAccordion>
    </div>
  );
}
