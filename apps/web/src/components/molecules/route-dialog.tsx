"use client";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Dialog, DialogContent, DialogTitle } from "@/components/atoms/dialog";

/** Intercepted routes preserve the directory and browser back/forward semantics. */
export function RouteDialog({ title, children }: { title: string; children: ReactNode }) {
  const router = useRouter();
  const t = useTranslations("corporate");
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) router.back();
      }}
    >
      <DialogContent
        closeLabel={t("close")}
        className="max-h-[calc(100dvh-2rem)] max-w-3xl overflow-y-auto"
      >
        <DialogTitle>{title}</DialogTitle>
        {children}
      </DialogContent>
    </Dialog>
  );
}
