"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import type { CorporateAssignContext } from "@/actions/corporate";
import { deleteObjectAction } from "@/actions/object-presentation";
import { visibilityConfirm, visibilityPlan } from "@/actions/github";
import { Button } from "@/components/atoms/button";
import { MenuItem } from "@/components/atoms/menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/atoms/dialog";
import { Input } from "@/components/atoms/input";
import type {
  ObjectActionLabels,
  ObjectVisibilityEdit,
} from "@/components/organisms/component-actions";
import { Link, useRouter } from "@/lib/i18n/navigation";
import { Icon } from "@/theme/icons";

export type PrivilegedObjectMenuProps = {
  labels: ObjectActionLabels;
  editHref?: string | undefined;
  manageAccessHref?: string | undefined;
  hasOwnerEdit: boolean;
  onOwnerOpen: () => void;
  visibilityEdit?: ObjectVisibilityEdit | undefined;
  onVisibilityOpen: () => void;
  assignCtx: CorporateAssignContext | null;
  onAssignOpen: () => void;
  objectDelete?:
    { csrfToken: string; locale: string; catalogHref: string; stableId: string } | undefined;
  objectKind: "component" | "setup";
};

/** Capability-gated menu items: edit, access, ownership, visibility, assign, delete. */
export function PrivilegedObjectMenuItems({
  labels,
  editHref,
  manageAccessHref,
  hasOwnerEdit,
  onOwnerOpen,
  visibilityEdit,
  onVisibilityOpen,
  assignCtx,
  onAssignOpen,
  objectDelete,
  objectKind,
}: PrivilegedObjectMenuProps) {
  return (
    <>
      {editHref ? (
        <MenuItem asChild>
          <Link href={editHref}>
            <Icon name="edit" size="sm" />
            {labels.editPresentation ?? "Edit public presentation"}
          </Link>
        </MenuItem>
      ) : null}
      {manageAccessHref ? (
        <MenuItem asChild>
          <Link href={manageAccessHref} prefetch={false}>
            <Icon name="access" size="sm" />
            {labels.manageAccess ?? "Manage access"}
          </Link>
        </MenuItem>
      ) : null}
      {hasOwnerEdit ? (
        <MenuItem
          onSelect={() => {
            onOwnerOpen();
          }}
        >
          <Icon name="edit" size="sm" />
          {labels.edit ?? "Edit"}
        </MenuItem>
      ) : null}
      {visibilityEdit ? (
        <MenuItem
          onSelect={() => {
            onVisibilityOpen();
          }}
        >
          <Icon name={visibilityEdit.visibility === "public" ? "lock" : "globe"} size="sm" />
          {visibilityEdit.visibility === "public"
            ? visibilityEdit.labels.removeFromPublic
            : visibilityEdit.labels.goPublic}
        </MenuItem>
      ) : null}
      {assignCtx?.ok ? (
        <MenuItem
          onSelect={() => {
            onAssignOpen();
          }}
        >
          <Icon name="team" size="sm" />
          {assignCtx.labels.assign}
        </MenuItem>
      ) : null}
      {objectDelete ? (
        <ObjectDeleteMenuItem labels={labels} objectDelete={objectDelete} objectKind={objectKind} />
      ) : null}
    </>
  );
}

function ObjectDeleteMenuItem({
  labels,
  objectDelete,
  objectKind,
}: {
  labels: ObjectActionLabels;
  objectDelete: { csrfToken: string; locale: string; catalogHref: string; stableId: string };
  objectKind: "component" | "setup";
}) {
  const router = useRouter();
  const [deleting, startDeleteTransition] = useTransition();
  return (
    <MenuItem
      className="text-destructive"
      disabled={deleting}
      onSelect={(event) => {
        event.preventDefault();
        if (!window.confirm(labels.confirmDelete ?? "Delete this object?")) return;
        startDeleteTransition(async () => {
          const result = await deleteObjectAction({
            csrfToken: objectDelete.csrfToken,
            stableId: objectDelete.stableId,
            objectKind,
            locale: objectDelete.locale,
          });
          if (!result.ok) {
            toast.error(result.message);
            return;
          }
          toast.success(labels.deleted ?? labels.delete ?? "Deleted");
          router.push(objectDelete.catalogHref);
        });
      }}
    >
      <Icon name="close" size="sm" />
      {deleting ? "…" : (labels.delete ?? "Delete")}
    </MenuItem>
  );
}

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
