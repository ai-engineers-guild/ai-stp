export type ContextCostLabels = {
  title: string;
  rateLabel: string;
  estimate: string;
  empty: string;
  invalid: string;
  hint: string;
};

export type ContextBudgetLabels = {
  title: string;
  lead: string;
  always: string;
  alwaysHint: string;
  conditional: string;
  conditionalHint: string;
  total: string;
  unavailable: string;
  empty: string;
  error: string;
  tokens: string;
  checkLocally: string;
  localCommandTitle: string;
  localCommandBody: string;
  copy: string;
  copied: string;
  copyError: string;
  docs: string;
  cost: ContextCostLabels;
};

export function contextBudgetLabels(
  t: (key: string) => string,
  tCli: (key: string) => string,
): ContextBudgetLabels {
  return {
    title: t("contextBudgetTitle"),
    lead: t("contextBudgetLead"),
    always: t("contextBudgetAlways"),
    alwaysHint: t("contextBudgetAlwaysHint"),
    conditional: t("contextBudgetConditional"),
    conditionalHint: t("contextBudgetConditionalHint"),
    total: t("contextBudgetTotal"),
    unavailable: t("contextBudgetUnavailable"),
    empty: t("contextBudgetEmpty"),
    error: t("contextBudgetError"),
    tokens: t("contextBudgetTokens"),
    checkLocally: t("contextBudgetCheckLocally"),
    localCommandTitle: t("localImpactCommandTitle"),
    localCommandBody: t("localImpactCommandBody"),
    copy: tCli("copy"),
    copied: tCli("copied"),
    copyError: tCli("copyError"),
    docs: tCli("docs"),
    cost: {
      title: t("contextCostTitle"),
      rateLabel: t("contextCostRateLabel"),
      estimate: t("contextCostEstimate"),
      empty: t("contextCostEmpty"),
      invalid: t("contextCostInvalid"),
      hint: t("contextCostHint"),
    },
  };
}
