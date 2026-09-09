"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { visibilityConfirm, visibilityPlan } from "@/actions/github";
import { Button } from "@/components/atoms/button";
import { CatalogItemMenu } from "@/components/organisms/catalog-item-menu";
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
  const tc = useTranslations("catalog");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [typedName, setTypedName] = useState("");
  const [error, setError] = useState("");
  const [busy, start] = useTransition();
  const target = props.visibility === "public" ? "private" : "public";
  const canChange = props.kind === "component" && Boolean(props.version && props.deviceId);
  const publicHref = `/catalog/${props.kind === "component" ? "components" : "setups"}/${props.stableId}`;

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
      <CatalogItemMenu
        kind={props.kind}
        stableId={props.stableId}
        version={props.version}
        href={publicHref}
        labels={{
          more: t("manageObject"),
          copyUrl: tc("copyUrl"),
          copyCli: tc("copyCli"),
          copyId: tc("copyId"),
          copied: tc("copied"),
          report: props.kind === "setup" ? tc("reportSetup") : tc("report"),
          like: tc("likeMenu"),
          unlike: tc("unlikeMenu"),
        }}
        leadingItems={[
          ...(props.visibility === "public"
            ? [
                <DropdownMenu.Item key="view" asChild>
                  <Link className={menuItemClassName} href={publicHref} prefetch={false}>
                    {t("viewPublic")}
                  </Link>
                </DropdownMenu.Item>,
              ]
            : []),
          ...(canChange
            ? [
                <DropdownMenu.Item key="visibility" asChild>
                  <button
                    className={menuItemClassName}
                    type="button"
                    onClick={() => {
                      setOpen(true);
                    }}
                  >
                    {target === "public" ? t("makePublic") : t("makePrivate")}
                  </button>
                </DropdownMenu.Item>,
              ]
            : []),
          <DropdownMenu.Item key="edit" asChild>
            <Link
              className={menuItemClassName}
              href={`/objects/${props.kind}/${props.stableId}/edit`}
            >
              {t("editPresentation")}
            </Link>
          </DropdownMenu.Item>,
          <DropdownMenu.Item key="access" asChild>
            <Link
              className={menuItemClassName}
              href={`/access?object_kind=${props.kind}&stable_id=${encodeURIComponent(props.stableId)}`}
            >
              {t("manageAccess")}
            </Link>
          </DropdownMenu.Item>,
        ]}
      />
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
