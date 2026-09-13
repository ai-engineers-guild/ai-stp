/** Navigation visibility is not authorization; endpoints still enforce scoped access. */
export function canViewCorporateAdministration(capabilities: readonly string[]): boolean {
  return capabilities.some(
    (permission) =>
      /^(role\.|binding\.|service_principal\.|audit\.)/.test(permission) ||
      permission === "member.update" ||
      permission === "member.delete" ||
      permission === "landscape.manage",
  );
}

export function canViewCorporateSection(key: string, capabilities: readonly string[]): boolean {
  if (key === "admins") return canViewCorporateAdministration(capabilities);
  const permission = {
    employees: "member.list",
    projects: "project.list",
    teams: "team.list",
    technologies: "technology.list",
    categories: "category.list",
  }[key];
  return permission !== undefined && capabilities.includes(permission);
}
