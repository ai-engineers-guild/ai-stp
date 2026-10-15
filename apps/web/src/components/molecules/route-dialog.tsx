"use client";
import { returnFromEditor } from "@/lib/navigation-history";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Dialog, DialogContent, DialogTitle } from "@/components/atoms/dialog";

/** Intercepted routes preserve the directory and browser back/forward semantics. */
export function RouteDialog({
  title,
  children,
  fallback = "/corporate/overview",
}: {
  title: string;
  children: ReactNode;
  fallback?: string;
}) {
  const router = useRouter();
  const t = useTranslations("corporate");
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) returnFromEditor(router, fallback);
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
