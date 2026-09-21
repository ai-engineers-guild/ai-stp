import type {
  ObjectActionLabels,
  ObjectVisibilityEdit,
} from "@/components/organisms/component-actions";

type Translate = (key: string) => string;

/** Shared catalog-object action menu labels (catalog, objects, hub namespaces). */
export function objectActionLabels({
  catalog,
  objects,
  hub,
  report,
}: {
  catalog: Translate;
  objects: Translate;
  hub: Translate;
  report: string;
}): ObjectActionLabels {
  return {
    copyUrl: catalog("copyUrl"),
    share: catalog("share"),
    copyId: catalog("copyId"),
    copyCli: catalog("copyCli"),
    copied: catalog("copied"),
    like: catalog("like"),
    unlike: catalog("unlike"),
    likeMenu: catalog("likeMenu"),
    unlikeMenu: catalog("unlikeMenu"),
    more: catalog("moreActions"),
    report,
    openDetails: hub("openDetails"),
    editPresentation: objects("editPresentation"),
    edit: hub("edit"),
    manageAccess: objects("manageAccess"),
    delete: catalog("objectDelete"),
    confirmDelete: catalog("objectDeleteConfirm"),
    deleted: catalog("objectDeleted"),
  };
}

/** Labels for the visibility toggle dialog, resolved for the current direction. */
export function objectVisibilityLabels(
  objects: Translate,
  visibility: "public" | "private",
): ObjectVisibilityEdit["labels"] {
  const toPublic = visibility !== "public";
  return {
    goPublic: objects("makePublic"),
    removeFromPublic: objects("makePrivate"),
    title: objects(toPublic ? "makePublicTitle" : "makePrivateTitle"),
    description: objects(toPublic ? "makePublicDescription" : "makePrivateDescription"),
    ...(toPublic ? { typeObjectName: objects("typeObjectName") } : {}),
    confirm: objects("confirmVisibility"),
    cancel: objects("cancel"),
    busy: objects("changingVisibility"),
    failed: objects("visibilityFailed"),
  };
}
