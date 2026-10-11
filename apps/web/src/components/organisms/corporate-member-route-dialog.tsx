"use client";
import { useRouter } from "next/navigation";
import { EditMemberDialog } from "@/components/organisms/corporate-member-edit-dialogs";
import type { ComponentProps } from "react";
export function CorporateMemberRouteDialog(
  props: Omit<ComponentProps<typeof EditMemberDialog>, "onClose">,
) {
  const router = useRouter();
  return (
    <EditMemberDialog
      {...props}
      onClose={() => {
        router.back();
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
        if (!open) router.back();
      }}
    />
  );
}
