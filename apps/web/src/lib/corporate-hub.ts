/** Navigation visibility is not authorization; endpoints still enforce scoped access. */
export function canViewCorporateAdministration(capabilities: readonly string[]): boolean {
  return capabilities.some(
    (permission) =>
      /^(role\.|binding\.|service_principal\.|audit\.|job_title\.)/.test(permission) ||
      permission === "member.update" ||
      permission === "member.delete" ||
      permission === "landscape.manage",
  );
}

export function canViewCorporateSection(key: string, capabilities: readonly string[]): boolean {
  if (key === "admins") return canViewCorporateAdministration(capabilities);
  if (key === "components") {
    return capabilities.includes("project.list") || capabilities.includes("member.list");
  }
  const permission = CORPORATE_SECTION_PERMISSIONS[key];
  return permission !== undefined && capabilities.includes(permission);
}

export const CORPORATE_SECTION_PERMISSIONS: Readonly<Record<string, string>> = {
  employees: "member.list",
  projects: "project.list",
  teams: "team.list",
  technologies: "technology.list",
  categories: "category.list",
  mappings: "technology.list",
  reports: "telemetry.read",
};
