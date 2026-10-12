"use client";
import { returnFromEditor } from "@/lib/navigation-history";
import { useRouter } from "next/navigation";
import { EditMemberDialog } from "@/components/organisms/corporate-member-edit-dialogs";
import { useState, useTransition, type ComponentProps } from "react";
import { useTranslations } from "next-intl";
import { MenuItem } from "@/components/atoms/menu";
import { loadCorporateGrantDialog } from "@/actions/entity-actions";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";
import { toast } from "sonner";
export function CorporateMemberRouteDialog(
  props: Omit<ComponentProps<typeof EditMemberDialog>, "onClose">,
) {
  const router = useRouter();
  return (
    <EditMemberDialog
      {...props}
      onClose={() => {
        returnFromEditor(router, `/corporate/employees/${props.member?.account_id ?? ""}`);
      }}
    />
  );
}

import { CorporateGrantAccessDialog } from "@/components/organisms/corporate-grant-access-dialog";
export function CorporateGrantRouteDialog(
  props: Omit<ComponentProps<typeof CorporateGrantAccessDialog>, "open" | "onOpenChange">,
) {
  const router = useRouter();
  return (
    <CorporateGrantAccessDialog
      {...props}
      open
      onOpenChange={(open) => {
        if (!open) returnFromEditor(router, "/corporate/employees");
      }}
    />
  );
}

export function CorporateGrantMenuAction({ subject }: { subject: EntityActionSubject }) {
  const objects = useTranslations("objects");
  const common = useTranslations("common");
  const [context, setContext] = useState<Awaited<
    ReturnType<typeof loadCorporateGrantDialog>
  > | null>(null);
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  return (
    <>
      <MenuItem
        disabled={pending}
        onSelect={(event) => {
          event.preventDefault();
          start(async () => {
            try {
              setContext(await loadCorporateGrantDialog(subject));
              setOpen(true);
            } catch {
              toast.error(common("requestFailed"));
            }
          });
        }}
      >
        <Icon name="access" size="sm" />
        {objects("manageAccess")}
      </MenuItem>
      {context && open ? (
        <CorporateGrantAccessDialog {...context} open={open} onOpenChange={setOpen} />
      ) : null}
    </>
  );
}
