"use client";

import { useEffect, useEffectEvent, useRef } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { queryEntityActionMenu } from "@/lib/entity-action-query";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";

/** Open a linked workspace operation only after the server confirms its current authority. */
export function useRequestedEntityAction(
  subject: EntityActionSubject | null,
  action: string,
  onAction: () => void,
) {
  const common = useTranslations("common");
  const open = useEffectEvent(onAction);
  const consumed = useRef("");
  const key = subject ? JSON.stringify(subject) : "";
  useEffect(() => {
    if (!key || !action || consumed.current === `${key}:${action}`) return;
    let current = true;
    void queryEntityActionMenu(JSON.parse(key) as EntityActionSubject)
      .then(({ menu }) => {
        if (current && menu.actions.some((item) => item.id === action)) {
          consumed.current = `${key}:${action}`;
          open();
        }
      })
      .catch(() => {
        if (current) toast.error(common("requestFailed"));
      });
    return () => {
      current = false;
    };
  }, [key, action, common]);
}
