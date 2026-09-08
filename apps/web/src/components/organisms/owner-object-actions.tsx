"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
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

const menuItemClassName =
  "hover:bg-muted focus:bg-muted flex min-h-11 w-full cursor-pointer items-center rounded-md px-3 py-2 text-left text-sm outline-none";

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
      if (!planned.ok) {
        setError(planned.code);
        return;
      }
      const applied = await visibilityConfirm(props.csrfToken, planned.data.plan_id, {
        plan_hash: planned.data.plan_hash,
        confirmed: true,
        idempotency_key: crypto.randomUUID(),
      });
      if (!applied.ok) {
        setError(applied.code);
        return;
      }
      setOpen(false);
      setTypedName("");
      router.refresh();
    });
  }

  return (
    <>
      <DropdownMenu.Root modal={false}>
        <DropdownMenu.Trigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="border-border bg-card/80 hover:bg-muted h-11 w-11 border shadow-sm transition-shadow hover:shadow-md focus-visible:ring-2"
            aria-label={t("manageObject")}
          >
            <Icon name="more" size="sm" />
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            side="bottom"
            align="end"
            sideOffset={4}
            collisionPadding={12}
            className="border-border bg-popover text-popover-foreground z-[80] grid max-w-[calc(100vw-1.5rem)] min-w-72 rounded-lg border p-1 shadow-md"
          >
            {canChange ? (
              <DropdownMenu.Item asChild>
                <button
                  className={menuItemClassName}
                  type="button"
                  onClick={() => {
                    setOpen(true);
                  }}
                >
                  {target === "public" ? t("makePublic") : t("makePrivate")}
                </button>
              </DropdownMenu.Item>
            ) : null}
            <DropdownMenu.Item asChild>
              <Link
                className={menuItemClassName}
                href={`/objects/${props.kind}/${props.stableId}/edit`}
              >
                {t("editPresentation")}
              </Link>
            </DropdownMenu.Item>
            <DropdownMenu.Item asChild>
              <Link className={menuItemClassName} href={`/objects/${props.kind}/${props.stableId}`}>
                {t("manageAccess")}
              </Link>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
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
                onChange={(event) => {
                  setTypedName(event.target.value);
                }}
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
            <Button
              variant="ghost"
              onClick={() => {
                setOpen(false);
              }}
            >
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
