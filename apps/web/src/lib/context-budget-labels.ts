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
  componentLead?: string;
  runtimeDerived?: string;
  always: string;
  alwaysHint: string;
  conditional: string;
  conditionalHint: string;
  total: string;
  unavailable: string;
  empty: string;
  error: string;
  artifactCorrupt?: string;
  invalidGraph?: string;
  dependencyFailure?: string;
  nonUtf8?: string;
  adaptationRequired?: string;
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
    componentLead: t("contextBudgetComponentLead"),
    runtimeDerived: t("contextBudgetRuntimeDerived"),
    always: t("contextBudgetAlways"),
    alwaysHint: t("contextBudgetAlwaysHint"),
    conditional: t("contextBudgetConditional"),
    conditionalHint: t("contextBudgetConditionalHint"),
    total: t("contextBudgetTotal"),
    unavailable: t("contextBudgetUnavailable"),
    empty: t("contextBudgetEmpty"),
    error: t("contextBudgetError"),
    artifactCorrupt: t("contextBudgetArtifactCorrupt"),
    invalidGraph: t("contextBudgetInvalidGraph"),
    dependencyFailure: t("contextBudgetDependencyFailure"),
    nonUtf8: t("contextBudgetNonUtf8"),
    adaptationRequired: t("contextBudgetAdaptationRequired"),
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

export function contextBudgetMessage(labels: ContextBudgetLabels, reason?: string | null): string {
  switch (reason) {
    case "artifact_corrupt":
    case "artifact_invalid":
      return labels.artifactCorrupt ?? labels.error;
    case "invalid_graph":
      return labels.invalidGraph ?? labels.error;
    case "dependency_unavailable":
      return labels.dependencyFailure ?? labels.error;
    case "content_is_not_utf8":
      return labels.nonUtf8 ?? labels.error;
    case "adaptation_selection_required":
      return labels.adaptationRequired ?? labels.error;
    default:
      return labels.error;
  }
}
