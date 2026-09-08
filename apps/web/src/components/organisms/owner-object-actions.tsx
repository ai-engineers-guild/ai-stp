"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { visibilityConfirm, visibilityPlan } from "@/actions/github";
import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/atoms/dialog";
import { Input } from "@/components/atoms/input";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type Props = {
  csrfToken: string;
  deviceId: string | null;
  kind: "component" | "setup";
  stableId: string;
  name: string;
  version: string | null;
  visibility: string;
};

export function OwnerObjectActions(props: Props) {
  const t = useTranslations("objects");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [typedName, setTypedName] = useState("");
  const [error, setError] = useState("");
  const [busy, start] = useTransition();
  const target = props.visibility === "public" ? "private" : "public";
  const canChange = props.kind === "component" && Boolean(props.version && props.deviceId);

  function confirm() {
    if (!props.version || !props.deviceId) return;
    const version = props.version;
    const deviceId = props.deviceId;
    setError("");
    start(async () => {
      const planned = await visibilityPlan(props.csrfToken, {
        object_kind: "component",
        stable_id: props.stableId,
        version,
        visibility: target,
        device_id: deviceId,
        idempotency_key: crypto.randomUUID(),
      });
      if (!planned.ok) { setError(planned.code); return; }
      const applied = await visibilityConfirm(props.csrfToken, planned.data.plan_id, {
        plan_hash: planned.data.plan_hash,
        confirmed: true,
        idempotency_key: crypto.randomUUID(),
      });
      if (!applied.ok) { setError(applied.code); return; }
      setOpen(false);
      setTypedName("");
      router.refresh();
    });
  }

  return (
    <>
      <details className="absolute top-4 right-4">
        <summary
          className="border-border hover:bg-muted flex size-11 cursor-pointer list-none items-center justify-center rounded-md border"
          aria-label={t("manageObject")}
        >
          <Icon name="more" size="sm" />
        </summary>
        <div className="border-border bg-popover absolute top-12 right-0 z-20 grid min-w-56 rounded-lg border p-1 shadow-md">
          {canChange ? (
            <button
              className="hover:bg-muted min-h-11 rounded-md px-3 py-2 text-left text-sm"
              type="button"
              onClick={() => { setOpen(true); }}
            >
              {target === "public" ? t("makePublic") : t("makePrivate")}
            </button>
          ) : null}
          <Link
            className="hover:bg-muted rounded-md px-3 py-2 text-sm"
            href={`/objects/${props.kind}/${props.stableId}/edit`}
          >
            {t("editPresentation")}
          </Link>
          <Link
            className="hover:bg-muted rounded-md px-3 py-2 text-sm"
            href={`/objects/${props.kind}/${props.stableId}`}
          >
            {t("manageAccess")}
          </Link>
        </div>
      </details>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent closeLabel={t("cancel")}>
          <DialogHeader>
            <DialogTitle>
              {target === "public" ? t("makePublicTitle") : t("makePrivateTitle")}
            </DialogTitle>
            <DialogDescription>
              {target === "public" ? t("makePublicDescription") : t("makePrivateDescription")}
            </DialogDescription>
          </DialogHeader>
          <p className="font-medium break-words">{props.name}</p>
          {target === "public" ? (
            <label className="space-y-2">
              <span className="text-sm">{t("typeObjectName")}</span>
              <Input
                value={typedName}
                onChange={(event) => { setTypedName(event.target.value); }}
                autoComplete="off"
              />
            </label>
          ) : null}
          {error ? (
            <p role="alert" className="text-destructive text-sm">
              {t("visibilityFailed")}
            </p>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => { setOpen(false); }}>
              {t("cancel")}
            </Button>
            <Button
              variant={target === "public" ? "default" : "destructive"}
              disabled={busy || (target === "public" && typedName !== props.name)}
              onClick={confirm}
            >
              {busy ? t("changingVisibility") : t("confirmVisibility")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
