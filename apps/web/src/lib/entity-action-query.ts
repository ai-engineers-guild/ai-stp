import { loadEntityActionMenus } from "@/actions/entity-actions";
import type { EntityActionMenu, EntityActionSubject } from "@/lib/api/generated/types.gen";

type Result = { menu: EntityActionMenu; csrfToken: string };
let pending: {
  subject: EntityActionSubject;
  resolve: (value: Result) => void;
  reject: (error: unknown) => void;
}[] = [];

/** Combine concurrent opens, without retaining permissions after the request. */
export function queryEntityActionMenu(subject: EntityActionSubject): Promise<Result> {
  return new Promise((resolve, reject) => {
    pending.push({ subject, resolve, reject });
    if (pending.length !== 1) return;
    queueMicrotask(() => {
      const requests = pending;
      pending = [];
      for (let offset = 0; offset < requests.length; offset += 256) {
        const batch = requests.slice(offset, offset + 256);
        void loadEntityActionMenus(batch.map((item) => item.subject))
          .then(({ menus, csrfToken }) => {
            if (menus.items.length !== batch.length)
              throw new Error("entity menu response mismatch");
            if (
              menus.items.some(
                (menu, index) =>
                  menu.subject.kind !== batch[index]?.subject.kind ||
                  menu.subject.id !== batch[index].subject.id,
              )
            )
              throw new Error("entity menu subject mismatch");
            batch.forEach((item, index) => {
              const menu = menus.items[index];
              if (!menu) throw new Error("entity menu response mismatch");
              item.resolve({ menu, csrfToken });
            });
          })
          .catch((error: unknown) => {
            batch.forEach((item) => {
              item.reject(error);
            });
          });
      }
    });
  });
}
