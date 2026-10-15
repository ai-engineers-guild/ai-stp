import type { EntityActionSubject, EntityActionMenu } from "@/lib/api/generated/types.gen";

const resourceKinds: Record<string, EntityActionSubject["kind"]> = {
  teams: "team",
  projects: "project",
  members: "member",
  employees: "member",
  technologies: "technology",
  categories: "category",
  areas: "area",
  "job-titles": "job_title",
  roles: "role",
};

export function entityActionSubject(target: string | undefined): EntityActionSubject | undefined {
  if (!target) return undefined;
  const [, resource, id] = target.split(":");
  const kind = resource ? resourceKinds[resource] : undefined;
  return kind && id ? { kind, id } : undefined;
}

/** Detail context changes navigation entries, never the principal's permissions. */
export function entityMenuContext(subject: EntityActionSubject): EntityActionSubject {
  if (typeof window === "undefined" || subject.view) return subject;
  const segments = window.location.pathname.split("/");
  const detailResources: Partial<Record<EntityActionSubject["kind"], string>> = {
    component: "components",
    setup: "setups",
    team: "teams",
    project: "projects",
    member: "employees",
    technology: "technologies",
    category: "categories",
    area: "areas",
    scan: "technology-scans",
    publisher: "publishers",
  };
  const resource = detailResources[subject.kind];
  return resource &&
    segments.some(
      (segment, index) =>
        segment === resource && segments[index + 1] === encodeURIComponent(subject.id),
    )
    ? { ...subject, view: "detail" }
    : subject;
}

export function entityActionEditHref(menu: EntityActionMenu, id: string, catalogObject: boolean) {
  const subject = menu.subject;
  return catalogObject
    ? `/objects/${subject.kind}/${subject.id}/edit`
    : subject.kind === "category"
      ? `/corporate/categories/${subject.id}/edit`
      : subject.kind === "area"
        ? `/corporate/areas/${subject.id}/edit`
        : subject.kind === "job_title"
          ? `/corporate/admin/job-titles?entity=${subject.id}&action=edit`
          : subject.kind === "role"
            ? `/corporate/admin/roles?entity=${encodeURIComponent(subject.id)}&action=edit`
            : `${menu.href}/${id === "edit_presentation" && ["member", "team", "project", "technology"].includes(subject.kind) ? "presentation/edit" : "edit"}`;
}
