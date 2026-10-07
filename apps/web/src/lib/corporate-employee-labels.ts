export type CorporateEmployeeDetailLabels = {
  profile: string;
  profileEmpty: string;
  profileUnavailable: string;
  noAccess: string;
  authoredSetups: string;
  noSetups: string;
  setupsUnavailable: string;
  authoredComponents: string;
  catalogItems?: string;
  noCatalogItems?: string;
  noComponents: string;
  componentsUnavailable: string;
  version: string;
  technologies: string;
  noTechnologies: string;
  technologiesUnavailable: string;
  leadStatus: string;
  notLead: string;
};

export function corporateEmployeeDetailLabels(
  t: (key: string) => string,
): CorporateEmployeeDetailLabels {
  return {
    profile: t("employeePublicProfile"),
    profileEmpty: t("employeeProfileEmpty"),
    profileUnavailable: t("employeeProfileUnavailable"),
    noAccess: t("employeeNoAccess"),
    authoredSetups: t("employeeAuthoredSetups"),
    noSetups: t("employeeNoSetups"),
    setupsUnavailable: t("employeeSetupsUnavailable"),
    authoredComponents: t("employeeAuthoredComponents"),
    catalogItems: t("employeeComponentsAndSetups"),
    noCatalogItems: t("employeeNoComponentsAndSetups"),
    noComponents: t("employeeNoComponents"),
    componentsUnavailable: t("employeeComponentsUnavailable"),
    version: t("employeeVersion"),
    technologies: t("employeeTechnologies"),
    noTechnologies: t("employeeNoTechnologies"),
    technologiesUnavailable: t("employeeTechnologiesUnavailable"),
    leadStatus: t("employeeLeadStatus"),
    notLead: t("employeeNotLead"),
  };
}
