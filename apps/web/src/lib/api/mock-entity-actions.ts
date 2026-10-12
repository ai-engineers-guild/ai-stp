/** Fixed menu responses for disposable offline fixtures; production decisions live in the API. */
import { errorBody, FIXTURE_DEVICE_ID } from "@/mocks/fixtures";
import { FIXTURE_COMPONENT_ID } from "@/mocks/fixtures/catalog-ids";
import type { EntityActionMenu, EntityActionSubject, EntityAction } from "./generated/types.gen";
import type { WorkspaceMockResult } from "./mock-workspace";
const routes: Partial<Record<EntityActionSubject["kind"], string>> = {
  team: "teams",
  project: "projects",
  member: "employees",
  technology: "technologies",
  category: "categories",
  area: "areas",
  job_title: "admin/job-titles",
  role: "admin/roles",
};
// eslint-disable-next-line complexity -- Fixed offline response inventory includes every menu family.
function fixtureMenu(subject: EntityActionSubject, authenticated: boolean): EntityActionMenu {
  const object = subject.kind === "component" || subject.kind === "setup";
  const ids = [
    "open",
    "copy_id",
    "copy_url",
    ...(object || subject.kind === "publisher" ? ["copy_cli"] : []),
    "share",
  ];
  if (object && authenticated) {
    ids.push("like");
    if (subject.id === FIXTURE_COMPONENT_ID) ids.push("edit_presentation", "manage_access");
  }
  if (routes[subject.kind] && authenticated) {
    if (!(subject.kind === "role" && ["superadmin", "staff", "lead"].includes(subject.id)))
      ids.push("edit");
    if (["team", "project", "member", "technology"].includes(subject.kind))
      ids.push("edit_presentation");
    if (subject.kind === "member") ids.push("manage_access");
    if (subject.kind === "job_title") ids.push("assign_members", "retire");
    if (subject.kind === "category") ids.push("manage_technologies");
    if (subject.kind === "role") ids.push("duplicate", "assign_members");
    if (
      ["team", "project", "member", "technology", "category", "area"].includes(subject.kind) ||
      (subject.kind === "role" && !["superadmin", "staff", "lead"].includes(subject.id))
    )
      ids.push("delete");
  }
  if (subject.kind === "grant") ids.splice(0, ids.length, "copy_id", "revoke");
  if (subject.kind === "invitation") ids.splice(0, ids.length, "copy_id", "revoke");
  if (subject.kind === "scan")
    ids.splice(0, ids.length, "open", ...(authenticated ? ["delete"] : []));
  if (subject.kind === "area")
    ids.splice(
      0,
      ids.length,
      "open",
      ...(subject.view === "landscape" ? ["expand_all", "collapse_all", "open_technologies"] : []),
      ...(authenticated ? ["edit", "delete"] : []),
    );
  if (subject.kind === "finding")
    ids.splice(
      0,
      ids.length,
      "evidence",
      "edit_technology",
      "create_technology",
      "move_to_dependencies",
    );
  if (!["scan", "finding", "invitation", "area"].includes(subject.kind)) ids.push("report");
  if (subject.view === "detail") ids.splice(ids.indexOf("open"), ids.includes("open") ? 1 : 0);
  if (authenticated && subject.assignment_id) ids.push("unlink");
  if (authenticated && subject.kind === "technology") ids.push("change_owner");
  const actions: EntityAction[] = ids.map((id) => ({
    id,
    group:
      id === "open" || id === "open_project" || id === "evidence"
        ? "navigation"
        : id === "report"
          ? "support"
          : ["revoke", "delete", "retire"].includes(id)
            ? "danger"
            : ["copy_id", "copy_url", "copy_cli", "share"].includes(id)
              ? "sharing"
              : "management",
  }));
  return {
    subject,
    href: object
      ? `/catalog/${subject.kind === "component" ? "components" : "setups"}/${subject.id}`
      : subject.kind === "publisher"
        ? `/publishers/${subject.id}`
        : `/corporate/${routes[subject.kind] ?? "admin"}${["team", "project", "member", "technology", "category", "area"].includes(subject.kind) ? `/${subject.id}` : ""}`,
    revision: 1,
    authorization_revision: 1,
    object_version: object ? "1.0" : null,
    object_name: object ? "Fixture object" : null,
    visibility: object ? "private" : null,
    device_id: object && authenticated ? FIXTURE_DEVICE_ID : null,
    actions,
  };
}
export function entityActionFixture(
  method: string,
  path: string,
  authenticated: boolean,
  body: unknown,
): WorkspaceMockResult | null {
  if (method !== "POST" || path !== "/v1/entity-actions/query") return null;
  const subjects = (body as { subjects?: EntityActionSubject[] } | undefined)?.subjects;
  if (!subjects?.length || subjects.length > 256)
    return { status: 400, body: errorBody("AI_STP_VALIDATION_ERROR", "entity.menu") };
  if (
    !authenticated &&
    subjects.some((subject) => !["component", "setup", "publisher"].includes(subject.kind))
  )
    return { status: 401, body: errorBody("AI_STP_AUTH_REQUIRED", "entity.menu") };
  return {
    status: 200,
    body: {
      schema_version: 1,
      items: subjects.map((subject) => fixtureMenu(subject, authenticated)),
    },
    headers: { "Cache-Control": "no-store, private" },
  };
}
