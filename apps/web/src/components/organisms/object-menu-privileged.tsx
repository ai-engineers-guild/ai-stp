"use client";

import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { Icon } from "@/theme/icons";
import { MenuItem } from "@/components/atoms/menu";
import { loadCatalogOwnerEditor } from "@/actions/entity-actions";
import { corporateAssignContextAction, type CorporateAssignContext } from "@/actions/corporate";
import type { EntityActionMenu } from "@/lib/api/generated/types.gen";
import type { CorporateCatalogOwnerEdit } from "@/components/organisms/corporate-catalog-owner-editor";
import type { ObjectActionLabels } from "@/components/organisms/component-actions";
import { CorporateAssignDialog } from "@/components/organisms/corporate-assign-dialog";
import { CorporateCatalogOwnerDialog } from "@/components/organisms/corporate-catalog-owner-editor";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import { useState, useTransition } from "react";

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
import type { ObjectVisibilityEdit } from "@/components/organisms/component-actions";
import { useRouter } from "@/lib/i18n/navigation";

export function ObjectVisibilityDialog({
  open,
  onOpenChange,
  edit,
  objectKind,
  stableId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  edit: ObjectVisibilityEdit;
  objectKind: "component" | "setup";
  stableId: string;
}) {
  const router = useRouter();
  const [typedName, setTypedName] = useState("");
  const [error, setError] = useState("");
  const [busy, start] = useTransition();
  const toPublic = edit.visibility !== "public";

  function confirm() {
    const version = edit.version;
    const deviceId = edit.deviceId;
    setError("");
    start(async () => {
      const planned = await visibilityPlan(edit.csrfToken, {
        object_kind: objectKind,
        stable_id: stableId,
        version,
        visibility: toPublic ? "public" : "private",
        device_id: deviceId,
        idempotency_key: crypto.randomUUID(),
      });
      if (!planned.ok) {
        setError(planned.code);
        return;
      }
      const applied = await visibilityConfirm(edit.csrfToken, planned.data.plan_id, {
        plan_hash: planned.data.plan_hash,
        confirmed: true,
        idempotency_key: crypto.randomUUID(),
      });
      if (!applied.ok) {
        setError(applied.code);
        return;
      }
      onOpenChange(false);
      setTypedName("");
      router.refresh();
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={edit.labels.cancel}>
        <DialogHeader>
          <DialogTitle>{edit.labels.title}</DialogTitle>
          <DialogDescription>{edit.labels.description}</DialogDescription>
        </DialogHeader>
        <p className="font-medium break-words">{edit.name}</p>
        {toPublic && edit.labels.typeObjectName ? (
          <label className="space-y-2">
            <span className="text-sm">{edit.labels.typeObjectName}</span>
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
            {edit.labels.failed}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            {edit.labels.cancel}
          </Button>
          <Button
            variant={toPublic ? "default" : "destructive"}
            disabled={busy || (toPublic && typedName !== edit.name)}
            onClick={confirm}
          >
            {busy ? edit.labels.busy : edit.labels.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function useObjectMenuExecution(
  stableId: string,
  ownerEdit: CorporateCatalogOwnerEdit | undefined,
  visibilityEdit: ObjectVisibilityEdit | undefined,
) {
  const objects = useTranslations("objects");
  const common = useTranslations("common");
  const [execution, setExecution] = useState<{ menu: EntityActionMenu; csrfToken: string } | null>(
    null,
  );
  const [loadedOwner, setLoadedOwner] = useState<CorporateCatalogOwnerEdit | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [assignCtx, setAssignCtx] = useState<CorporateAssignContext | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);
  const [ownerOpen, setOwnerOpen] = useState(false);
  const [visibilityOpen, setVisibilityOpen] = useState(false);
  const effectiveOwner = loadedOwner ?? ownerEdit;
  const effectiveVisibility =
    execution?.menu.device_id && execution.menu.object_version && execution.menu.visibility
      ? {
          csrfToken: execution.csrfToken,
          deviceId: execution.menu.device_id,
          version: execution.menu.object_version,
          name: execution.menu.object_name ?? stableId,
          visibility: execution.menu.visibility,
          labels: {
            goPublic: objects("makePublic"),
            removeFromPublic: objects("makePrivate"),
            title: objects(
              execution.menu.visibility === "public" ? "makePrivateTitle" : "makePublicTitle",
            ),
            description: objects(
              execution.menu.visibility === "public"
                ? "makePrivateDescription"
                : "makePublicDescription",
            ),
            ...(execution.menu.visibility !== "public"
              ? { typeObjectName: objects("typeObjectName") }
              : {}),
            confirm: objects("confirmVisibility"),
            cancel: objects("cancel"),
            busy: objects("changingVisibility"),
            failed: objects("visibilityFailed"),
          },
        }
      : visibilityEdit;
  async function openOwner() {
    if (!execution?.menu.object_version) return;
    try {
      setLoadedOwner(
        await loadCatalogOwnerEditor(execution.menu.subject, execution.menu.object_version),
      );
      setOwnerOpen(true);
    } catch {
      toast.error(common("requestFailed"));
    }
  }
  async function openAssignment() {
    try {
      const context = await corporateAssignContextAction();
      if (!context.ok) throw new Error("assignment unavailable");
      setAssignCtx(context);
      setAssignOpen(true);
    } catch {
      toast.error(common("requestFailed"));
    }
  }
  return {
    execution,
    setExecution,
    effectiveOwner,
    effectiveVisibility,
    reportOpen,
    setReportOpen,
    assignCtx,
    assignOpen,
    setAssignOpen,
    ownerOpen,
    setOwnerOpen,
    visibilityOpen,
    setVisibilityOpen,
    openOwner,
    openAssignment,
  };
}

export function CatalogShareMenuItem({
  path,
  canonicalUrl,
  labels,
}: {
  path: string;
  canonicalUrl: string | undefined;
  labels: ObjectActionLabels;
}) {
  async function share() {
    const url = canonicalUrl ?? new URL(path, location.origin).toString();
    const nativeShare: unknown = Reflect.get(navigator, "share");
    if (typeof nativeShare === "function") {
      try {
        await Reflect.apply(nativeShare, navigator, [{ url }]);
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
      }
    }
    await navigator.clipboard.writeText(url);
    toast.success(labels.copied);
  }
  return (
    <MenuItem
      onSelect={() => {
        void share();
      }}
    >
      <Icon name="link" size="sm" />
      {labels.share}
    </MenuItem>
  );
}

export function ObjectMenuDialogs({
  execution,
  editOpen,
  setEditOpen,
  canChangeOwner,
  canAssign,
  objectKind,
  stableId,
  objectName,
  labels,
}: {
  execution: Pick<
    ReturnType<typeof useObjectMenuExecution>,
    | "execution"
    | "openOwner"
    | "openAssignment"
    | "assignCtx"
    | "assignOpen"
    | "setAssignOpen"
    | "effectiveOwner"
    | "ownerOpen"
    | "setOwnerOpen"
    | "effectiveVisibility"
    | "visibilityOpen"
    | "setVisibilityOpen"
    | "reportOpen"
    | "setReportOpen"
  >;
  editOpen: boolean;
  setEditOpen: (open: boolean) => void;
  canChangeOwner: boolean;
  canAssign: boolean;
  objectKind: "component" | "setup";
  stableId: string;
  objectName: string | undefined;
  labels: ObjectActionLabels;
}) {
  const {
    assignCtx,
    assignOpen,
    setAssignOpen,
    effectiveOwner,
    ownerOpen,
    setOwnerOpen,
    effectiveVisibility,
    visibilityOpen,
    setVisibilityOpen,
    reportOpen,
    setReportOpen,
  } = execution;
  const hub = useTranslations("hub");
  return (
    <>
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{hub("edit")}</DialogTitle>
            <DialogDescription>{hub("catalogEditDescription")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            {canChangeOwner ? (
              <Button
                type="button"
                variant="outline"
                disabled={!execution.execution}
                onClick={() => {
                  setEditOpen(false);
                  void execution.openOwner();
                }}
              >
                {hub("assignOwner")}
              </Button>
            ) : null}
            {canAssign ? (
              <Button
                type="button"
                variant="outline"
                disabled={!execution.execution}
                onClick={() => {
                  setEditOpen(false);
                  void execution.openAssignment();
                }}
              >
                {hub("assign")}
              </Button>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
      {assignCtx?.ok ? (
        <CorporateAssignDialog
          open={assignOpen}
          onOpenChange={setAssignOpen}
          context={assignCtx}
          objectKind={objectKind}
          stableId={stableId}
          objectName={objectName ?? stableId}
        />
      ) : null}
      {effectiveOwner ? (
        <CorporateCatalogOwnerDialog
          open={ownerOpen}
          onOpenChange={setOwnerOpen}
          ownerEdit={effectiveOwner}
        />
      ) : null}
      {effectiveVisibility ? (
        <ObjectVisibilityDialog
          open={visibilityOpen}
          onOpenChange={setVisibilityOpen}
          edit={effectiveVisibility}
          objectKind={objectKind}
          stableId={stableId}
        />
      ) : null}
      {reportOpen ? (
        <ContactReportDialog
          kind={objectKind}
          target={stableId}
          label={labels.report}
          open={reportOpen}
          onOpenChange={setReportOpen}
          hideTrigger
        />
      ) : null}
    </>
  );
}
