"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import {
  EntityActionItems,
  usePreloadedEntityMenu,
} from "@/components/organisms/entity-action-items";
import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";
import {
  useObjectMenuExecution,
  CatalogShareMenuItem,
  ObjectMenuDialogs,
} from "@/components/organisms/object-menu-privileged";
import { type CorporateCatalogOwnerEdit } from "@/components/organisms/corporate-catalog-owner-editor";
import { useCatalogLike, type LikeState } from "@/lib/use-catalog-like";
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
  assignmentId?: string;
  onUnlink?: () => void;
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
      {like.liked ? labels.unlike : labels.like}
      {" · "}
      {like.count}
    </Button>
  );
}

// eslint-disable-next-line max-lines-per-function -- The catalog menu binds backend actions to their dialogs.
export function ObjectOverflowMenu({
  stableId,
  objectKind = "component",
  sharePath,
  likesCount,
  initiallyLiked = false,
  labels,
  cliCommand,
  canonicalUrl,
  objectName,
  ownerEdit,
  visibilityEdit,
  assignmentId,
  onUnlink,
}: ObjectActionProps) {
  const subject = {
    kind: objectKind,
    id: stableId,
    ...(assignmentId ? { assignment_id: assignmentId } : {}),
  };
  const preloaded = usePreloadedEntityMenu(subject);
  const behavior = useObjectMenuExecution(stableId, ownerEdit, visibilityEdit);
  const { execution, setExecution, setReportOpen, setVisibilityOpen, openOwner, openAssignment } =
    behavior;
  const [editOpen, setEditOpen] = useState(false);
  const activeMenu = execution?.menu ?? preloaded?.menu;
  const corporateEdit = Boolean(activeMenu?.subject.organization_id);
  const canChangeOwner = activeMenu?.actions.some((action) => action.id === "change_owner");
  const canAssign = activeMenu?.actions.some((action) => action.id === "assign");
  const like = useLikeState({
    stableId,
    objectKind,
    likesCount,
    initiallyLiked,
    labels,
  });
  const hub = useTranslations("hub");
  const objects = useTranslations("objects");
  const likeMenu = labels.likeMenu ?? labels.like;

  async function copy(value: string) {
    await navigator.clipboard.writeText(value);
    toast.success(labels.copied);
  }

  return (
    <>
      <Menu modal={false}>
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
          <EntityActionItems
            initialResult={preloaded}
            subject={subject}
            onLoaded={(menu, csrfToken) => {
              setExecution({ menu, csrfToken });
            }}
            entries={{
              edit: corporateEdit ? (
                <MenuItem
                  onSelect={(event) => {
                    event.preventDefault();
                    if (!execution && preloaded) setExecution(preloaded);
                    setEditOpen(true);
                  }}
                >
                  <Icon name="edit" size="sm" />
                  {hub("edit")}
                </MenuItem>
              ) : null,
              unlink: onUnlink ? (
                <MenuItem onSelect={onUnlink}>
                  <Icon name="close" size="sm" />
                  {hub("unlink")}
                </MenuItem>
              ) : null,
              copy_url: (
                <MenuItem
                  onSelect={() => {
                    void copy(canonicalUrl ?? new URL(sharePath, location.origin).toString());
                  }}
                >
                  <Icon name="link" size="sm" />
                  {labels.copyUrl}
                </MenuItem>
              ),
              share: (
                <CatalogShareMenuItem
                  path={sharePath}
                  canonicalUrl={canonicalUrl}
                  labels={labels}
                />
              ),
              change_owner: (
                <MenuItem
                  onSelect={() => {
                    void openOwner();
                  }}
                >
                  <Icon name="edit" size="sm" />
                  {hub("assignOwner")}
                </MenuItem>
              ),
              visibility: (
                <MenuItem
                  onSelect={() => {
                    setVisibilityOpen(true);
                  }}
                >
                  <Icon name="globe" size="sm" />
                  {execution?.menu.visibility === "public"
                    ? objects("makePrivate")
                    : objects("makePublic")}
                </MenuItem>
              ),
              assign: (
                <MenuItem
                  onSelect={() => {
                    void openAssignment();
                  }}
                >
                  <Icon name="team" size="sm" />
                  {hub("assign")}
                </MenuItem>
              ),
              copy_cli: cliCommand ? (
                <MenuItem
                  onSelect={() => {
                    void copy(cliCommand);
                  }}
                >
                  <Icon name="code" size="sm" />
                  {labels.copyCli ?? "Copy CLI command"}
                </MenuItem>
              ) : null,
              like: (
                <MenuItem
                  disabled={like.pending}
                  onSelect={() => {
                    like.toggle();
                  }}
                >
                  <Icon name="heart" size="sm" fill={like.liked ? "currentColor" : "none"} />
                  {like.liked ? (labels.unlikeMenu ?? "Unlike") : likeMenu}
                </MenuItem>
              ),
              report: (
                <MenuItem
                  onSelect={() => {
                    setReportOpen(true);
                  }}
                >
                  <Icon name="flag" size="sm" />
                  {labels.report}
                </MenuItem>
              ),
            }}
          />
        </MenuContent>
      </Menu>
      <ObjectMenuDialogs
        execution={behavior}
        editOpen={editOpen}
        setEditOpen={setEditOpen}
        canChangeOwner={Boolean(canChangeOwner)}
        canAssign={Boolean(canAssign)}
        objectKind={objectKind}
        stableId={stableId}
        objectName={objectName}
        labels={labels}
      />
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
