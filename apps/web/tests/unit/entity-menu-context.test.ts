import { afterEach, expect, it } from "vitest";
import { entityMenuContext } from "@/lib/entity-action-subject";

afterEach(() => {
  window.history.replaceState({}, "", "/");
});
it.each([
  "component",
  "setup",
  "team",
  "project",
  "member",
  "technology",
  "category",
  "area",
  "scan",
] as const)("marks only the currently opened %s as detail", (kind) => {
  const subject = { kind, id: `${kind}_123` };
  const resources = {
    component: "catalog/components",
    setup: "catalog/setups",
    team: "corporate/teams",
    project: "corporate/projects",
    member: "corporate/employees",
    technology: "corporate/technologies",
    category: "corporate/categories",
    area: "corporate/areas",
    scan: "corporate/technology-scans",
  };
  window.history.replaceState({}, "", `/en/${resources[kind]}/${subject.id}`);
  expect(entityMenuContext(subject)).toEqual({ ...subject, view: "detail" });
  expect(entityMenuContext({ ...subject, id: `${kind}_456` })).toEqual({
    ...subject,
    id: `${kind}_456`,
  });
  expect(entityMenuContext({ ...subject, view: "landscape" })).toEqual({
    ...subject,
    view: "landscape",
  });
});
it("keeps publisher navigation when the same account is open as an employee", () => {
  window.history.replaceState({}, "", "/en/corporate/employees/account_123");
  expect(entityMenuContext({ kind: "publisher", id: "account_123" }).view).toBeUndefined();
});
it("handles malformed escaped paths without exposing another entity's details state", () => {
  window.history.replaceState({}, "", "/en/corporate/entities/%bad");
  expect(entityMenuContext({ kind: "component", id: "component_123" }).view).toBeUndefined();
});
