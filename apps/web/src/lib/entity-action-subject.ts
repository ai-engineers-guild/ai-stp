import type { EntityActionSubject } from "@/lib/api/generated/types.gen";

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
