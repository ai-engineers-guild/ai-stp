import { getTranslations } from "next-intl/server";
import type { ComponentProps } from "react";
import { CorporateResourceActions } from "@/components/organisms/corporate-resource-actions";

export async function LocalizedResourceActions(
  props: Omit<ComponentProps<typeof CorporateResourceActions>, "labels">,
) {
  const t = await getTranslations("corporate");
  return (
    <CorporateResourceActions
      {...props}
      labels={{
        title: t("actions"),
        name: t("name"),
        role: t("organizationRole"),
        parentRole: t("parentRole"),
        permissions: t("permissions"),
        state: t("state"),
        update: t("update"),
        saving: t("saving"),
        saved: t("saved"),
        delete: t("delete"),
        deleting: t("deleting"),
        confirmDelete: t("confirmDelete"),
        staff: t("staff"),
        lead: t("lead"),
        superadmin: t("superadmin"),
        active: t("active"),
        suspended: t("suspended"),
        archived: t("archived"),
      }}
    />
  );
}
