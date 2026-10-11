import type { EntityActionMenu, EntityActionSubject } from "@/lib/api/generated/types.gen";
export const publicActions = ["open", "copy_id", "copy_url", "share", "report"];
export const catalogActions = [
  "open",
  "copy_id",
  "copy_url",
  "copy_cli",
  "share",
  "like",
  "report",
];
export function entityMenuResult(subject: EntityActionSubject, ids: string[], href?: string) {
  const menu: EntityActionMenu = {
    subject,
    href: href ?? null,
    revision: 1,
    authorization_revision: 1,
    object_version: null,
    object_name: null,
    visibility: null,
    device_id: null,
    actions: ids.map((id) => ({
      id,
      group:
        id === "open"
          ? "navigation"
          : id === "report"
            ? "support"
            : id === "delete"
              ? "danger"
              : id.startsWith("copy") || id === "share"
                ? "sharing"
                : "management",
    })),
  };
  return { menu, csrfToken: "csrf" };
}
