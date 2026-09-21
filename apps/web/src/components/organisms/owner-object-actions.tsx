"use client";

import { useTranslations } from "next-intl";

import {
  ObjectOverflowMenu,
  type ObjectVisibilityEdit,
} from "@/components/organisms/component-actions";
import type { CorporateCatalogOwnerEdit } from "@/components/organisms/corporate-catalog-owner-editor";
import { registryCommand, registryVersion } from "@/lib/cli-copy";

type Props = {
  csrfToken: string;
  deviceId: string | null;
  kind: "component" | "setup";
  stableId: string;
  name: string;
  version: string | null;
  visibility: "public" | "private";
  locale?: string;
  likesCount?: number;
  initiallyLiked?: boolean;
  capabilities?: readonly string[];
  ownerEdit?: CorporateCatalogOwnerEdit;
};

/**
 * The catalog-object overflow menu for owner workspaces. Privileged entries are
 * gated on the capabilities probe the page performed per object.
 */
export function OwnerObjectActions(props: Props) {
  const t = useTranslations("objects");
  const tc = useTranslations("catalog");
  const th = useTranslations("hub");
  const href = `/catalog/${props.kind === "component" ? "components" : "setups"}/${props.stableId}`;
  const capabilities = props.capabilities ?? [];
  const canEdit = capabilities.includes("edit");
  const canEditPresentation = capabilities.includes("edit_presentation");
  const canDelete = capabilities.includes("delete");
  const canToggleVisibility =
    props.kind === "component" &&
    Boolean(props.version && props.deviceId) &&
    (canEdit || canEditPresentation);
  const visibilityEdit: ObjectVisibilityEdit | undefined =
    canToggleVisibility && props.version && props.deviceId
      ? {
          csrfToken: props.csrfToken,
          deviceId: props.deviceId,
          version: props.version,
          name: props.name,
          visibility: props.visibility,
          labels: {
            goPublic: t("makePublic"),
            removeFromPublic: t("makePrivate"),
            title: t(props.visibility === "public" ? "makePrivateTitle" : "makePublicTitle"),
            description: t(
              props.visibility === "public" ? "makePrivateDescription" : "makePublicDescription",
            ),
            ...(props.visibility !== "public" ? { typeObjectName: t("typeObjectName") } : {}),
            confirm: t("confirmVisibility"),
            cancel: t("cancel"),
            busy: t("changingVisibility"),
            failed: t("visibilityFailed"),
          },
        }
      : undefined;

  return (
    <ObjectOverflowMenu
      stableId={props.stableId}
      objectKind={props.kind}
      sharePath={href}
      likesCount={props.likesCount ?? 0}
      initiallyLiked={props.initiallyLiked ?? false}
      reportHref={href}
      openHref={href}
      cliCommand={
        props.version
          ? registryVersion(props.kind, props.stableId, props.version)
          : registryCommand(props.stableId)
      }
      objectName={props.name}
      {...(canEditPresentation
        ? { editHref: `/objects/${props.kind}/${props.stableId}/edit` }
        : {})}
      {...(canEdit || canEditPresentation
        ? {
            manageAccessHref: `/access?object_kind=${props.kind}&stable_id=${encodeURIComponent(props.stableId)}`,
          }
        : {})}
      {...(props.ownerEdit ? { ownerEdit: props.ownerEdit } : {})}
      {...(visibilityEdit ? { visibilityEdit } : {})}
      {...(canDelete
        ? {
            objectDelete: {
              csrfToken: props.csrfToken,
              locale: props.locale ?? "en",
              catalogHref: "/objects",
            },
          }
        : {})}
      labels={{
        copyUrl: tc("copyUrl"),
        share: tc("share"),
        copyId: tc("copyId"),
        copyCli: tc("copyCli"),
        copied: tc("copied"),
        like: tc("likeMenu"),
        unlike: tc("unlikeMenu"),
        more: t("manageObject"),
        report: props.kind === "setup" ? tc("reportSetup") : tc("report"),
        openDetails: th("openDetails"),
        editPresentation: t("editPresentation"),
        edit: th("edit"),
        manageAccess: t("manageAccess"),
        delete: tc("objectDelete"),
        confirmDelete: tc("objectDeleteConfirm"),
        deleted: tc("objectDeleted"),
      }}
    />
  );
}
