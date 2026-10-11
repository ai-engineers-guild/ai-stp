"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { corporateAssignContextAction, type CorporateAssignContext } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/atoms/menu";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import { CorporateAssignDialog } from "@/components/organisms/corporate-assign-dialog";
import {
  ObjectVisibilityDialog,
  PrivilegedObjectMenuItems,
} from "@/components/organisms/object-menu-privileged";
import {
  CorporateCatalogOwnerDialog,
  type CorporateCatalogOwnerEdit,
} from "@/components/organisms/corporate-catalog-owner-editor";
import { useCatalogLike, type LikeState } from "@/lib/use-catalog-like";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme/icons";

export type ObjectActionLabels = {
  copyUrl: string;
  share: string;
  copyId: string;
  copyCli?: string;
  copied: string;
  like: string;
  unlike: string;
  likeMenu?: string;
  unlikeMenu?: string;
  more: string;
  report: string;
  openDetails?: string;
  editPresentation?: string;
  edit?: string;
  manageAccess?: string;
  delete?: string;
  confirmDelete?: string;
  deleted?: string;
};

export type ObjectVisibilityEdit = {
  csrfToken: string;
  deviceId: string;
  version: string;
  name: string;
  visibility: "public" | "private";
  labels: {
    goPublic: string;
    removeFromPublic: string;
    title: string;
    description: string;
    typeObjectName?: string;
    confirm: string;
    cancel: string;
    busy: string;
    failed: string;
  };
};

export type ObjectActionProps = {
  stableId: string;
  objectKind?: "component" | "setup";
  sharePath: string;
  likesCount: number;
  initiallyLiked?: boolean;
  labels: ObjectActionLabels;
  reportHref: string | undefined;
  openHref?: string;
  editHref?: string;
  manageAccessHref?: string;
  cliCommand?: string;
  canonicalUrl?: string;
  objectName?: string;
  ownerEdit?: CorporateCatalogOwnerEdit;
  visibilityEdit?: ObjectVisibilityEdit;
  objectDelete?: { csrfToken: string; locale: string; catalogHref: string };
};

const LikeContext = createContext<LikeState | null>(null);

function useLikeState(props: {
  stableId: string;
  objectKind?: "component" | "setup";
  likesCount?: number;
  initiallyLiked?: boolean;
  labels: Pick<ObjectActionLabels, "like">;
}): LikeState {
  const ctx = useContext(LikeContext);
  const local = useCatalogLike(props);
  return ctx ?? local;
}

export function ObjectLikeProvider({
  children,
  ...props
}: ObjectActionProps & { children: ReactNode }) {
  const like = useCatalogLike(props);
  return <LikeContext.Provider value={like}>{children}</LikeContext.Provider>;
}

export function ObjectLikeControl({
  stableId,
  objectKind = "component",
  likesCount,
  initiallyLiked = false,
  labels,
}: Pick<
  ObjectActionProps,
  "stableId" | "objectKind" | "likesCount" | "initiallyLiked" | "labels"
>) {
  const like = useLikeState({
    stableId,
    objectKind,
    likesCount,
    initiallyLiked,
    labels,
  });

  return (
    <Button
      type="button"
      variant={like.liked ? "default" : "outline"}
      size="sm"
      className="min-h-11"
      aria-pressed={like.liked}
      disabled={like.pending}
      onClick={() => {
        like.toggle();
      }}
    >
      <Icon name="heart" size="sm" fill={like.liked ? "currentColor" : "none"} />
      {like.liked ? labels.unlike : labels.like} · {like.count}
    </Button>
  );
}

// eslint-disable-next-line max-lines-per-function
export function ObjectOverflowMenu({
  stableId,
  objectKind = "component",
  sharePath,
  likesCount,
  initiallyLiked = false,
  labels,
  openHref,
  editHref,
  manageAccessHref,
  cliCommand,
  canonicalUrl,
  objectName,
  ownerEdit,
  visibilityEdit,
  objectDelete,
}: ObjectActionProps) {
  const [reportOpen, setReportOpen] = useState(false);
  const [assignCtx, setAssignCtx] = useState<CorporateAssignContext | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);
  const [ownerOpen, setOwnerOpen] = useState(false);
  const [visibilityOpen, setVisibilityOpen] = useState(false);
  const like = useLikeState({
    stableId,
    objectKind,
    likesCount,
    initiallyLiked,
    labels,
  });
  const likeMenu = labels.likeMenu ?? labels.like;
  const unlikeMenu = labels.unlikeMenu ?? "Unlike";
  const hasPrivileged = Boolean(
    editHref || manageAccessHref || ownerEdit || visibilityEdit || assignCtx?.ok || objectDelete,
  );

  async function copy(value: string) {
    await navigator.clipboard.writeText(value);
    toast.success(labels.copied);
  }

  async function share() {
    const url = canonicalUrl ?? new URL(sharePath, location.origin).toString();
    const nativeShare = browserShare();
    if (nativeShare) {
      try {
        await nativeShare({ url });
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
      }
    }
    await copy(url);
  }

  return (
    <>
      <Menu
        modal={false}
        onOpenChange={(open) => {
          if (open && assignCtx === null) {
            void corporateAssignContextAction()
              .then(setAssignCtx)
              .catch(() => {
                /* A dropped probe keeps the assign entry disabled. */
              });
          }
        }}
      >
        <MenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-11"
            aria-label={labels.more}
          >
            <Icon name="moreVertical" size="sm" />
          </Button>
        </MenuTrigger>
        <MenuContent>
          {openHref ? (
            <MenuItem asChild>
              <Link href={openHref} prefetch={false}>
                <Icon name="eye" size="sm" />
                {labels.openDetails ?? "Open details"}
              </Link>
            </MenuItem>
          ) : null}
          <MenuItem
            disabled={like.pending}
            onSelect={() => {
              like.toggle();
            }}
          >
            <Icon name="heart" size="sm" fill={like.liked ? "currentColor" : "none"} />
            {like.liked ? unlikeMenu : likeMenu}
          </MenuItem>
          <MenuSeparator />
          <MenuItem
            onSelect={() => {
              void copy(stableId);
            }}
          >
            <Icon name="copy" size="sm" />
            {labels.copyId}
          </MenuItem>
          <MenuItem
            onSelect={() => {
              void copy(canonicalUrl ?? new URL(sharePath, location.origin).toString());
            }}
          >
            <Icon name="link" size="sm" />
            {labels.copyUrl}
          </MenuItem>
          {cliCommand ? (
            <MenuItem
              onSelect={() => {
                void copy(cliCommand);
              }}
            >
              <Icon name="code" size="sm" />
              {labels.copyCli ?? "Copy CLI command"}
            </MenuItem>
          ) : null}
          <MenuItem
            onSelect={() => {
              void share();
            }}
          >
            <Icon name="link" size="sm" />
            {labels.share}
          </MenuItem>
          {hasPrivileged ? <MenuSeparator /> : null}
          <PrivilegedObjectMenuItems
            labels={labels}
            editHref={editHref}
            manageAccessHref={manageAccessHref}
            hasOwnerEdit={Boolean(ownerEdit)}
            onOwnerOpen={() => {
              setOwnerOpen(true);
            }}
            visibilityEdit={visibilityEdit}
            onVisibilityOpen={() => {
              setVisibilityOpen(true);
            }}
            assignCtx={assignCtx}
            onAssignOpen={() => {
              setAssignOpen(true);
            }}
            objectDelete={objectDelete ? { ...objectDelete, stableId } : undefined}
            objectKind={objectKind}
          />
          <MenuSeparator />
          <MenuItem
            onSelect={() => {
              setReportOpen(true);
            }}
          >
            <Icon name="flag" size="sm" />
            {labels.report}
          </MenuItem>
        </MenuContent>
      </Menu>
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
      {ownerEdit ? (
        <CorporateCatalogOwnerDialog
          open={ownerOpen}
          onOpenChange={setOwnerOpen}
          ownerEdit={ownerEdit}
        />
      ) : null}
      {visibilityEdit ? (
        <ObjectVisibilityDialog
          open={visibilityOpen}
          onOpenChange={setVisibilityOpen}
          edit={visibilityEdit}
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

export function ComponentActions(props: ObjectActionProps) {
  return (
    <ObjectLikeProvider {...props}>
      <div data-ui={UI.component.actions} className="contents">
        <ObjectLikeControl
          stableId={props.stableId}
          objectKind={props.objectKind ?? "component"}
          likesCount={props.likesCount}
          initiallyLiked={props.initiallyLiked ?? false}
          labels={props.labels}
        />
        <div data-ui={UI.component.overflow} className="absolute top-0 right-0">
          <ObjectOverflowMenu {...props} />
        </div>
      </div>
    </ObjectLikeProvider>
  );
}

function browserShare(): ((data?: ShareData) => Promise<void>) | null {
  if (typeof navigator === "undefined") return null;
  const candidate: unknown = Reflect.get(navigator, "share");
  if (typeof candidate !== "function") return null;
  return async (data) => {
    await (Reflect.apply(candidate, navigator, [data]) as Promise<unknown>);
  };
}
