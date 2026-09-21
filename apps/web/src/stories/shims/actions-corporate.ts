/** Storybook no-op for corporate server actions. */
export type CorporateAssignLabels = {
  assign: string;
  dialogTitle: string;
  version: string;
  latest: string;
  search: string;
  closeFilters: string;
  loading: string;
  assignPartial: string;
  assignFailed: string;
  employee: string;
  team: string;
  project: string;
  technologies: string;
};

export type CorporateAssignContext =
  | {
      ok: true;
      organizationId: string;
      authorizationRevision: number;
      csrfToken: string;
      labels: CorporateAssignLabels;
    }
  | { ok: false };

export type CorporateAssignSubjectKind = "employee" | "team" | "project" | "technology";

export async function corporateAssignContextAction(): Promise<CorporateAssignContext> {
  return { ok: false };
}

export async function corporateMutationAction(_input: unknown): Promise<never> {
  throw new Error("corporate write unavailable in Storybook");
}

export async function corporateCatalogSearchAction(_input: unknown): Promise<never> {
  throw new Error("catalog search unavailable in Storybook");
}

export async function corporateCatalogVersionsAction(_input: unknown): Promise<never> {
  throw new Error("version listing unavailable in Storybook");
}

export async function corporateSubjectSearchAction(_input: unknown): Promise<never> {
  throw new Error("subject search unavailable in Storybook");
}

export async function corporateTeamAssignmentsAction(_input: unknown): Promise<never> {
  throw new Error("team assignments unavailable in Storybook");
}

export async function corporateAuditExportAction(_input: unknown): Promise<never> {
  throw new Error("audit export unavailable in Storybook");
}
