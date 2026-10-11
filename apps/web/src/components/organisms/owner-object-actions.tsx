"use client";

import { useTranslations } from "next-intl";

import { ObjectOverflowMenu } from "@/components/organisms/component-actions";
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
 * Owner workspaces use the same live server menu as every catalog card.
 */
export function OwnerObjectActions(props: Props) {
  const t = useTranslations("objects");
  const tc = useTranslations("catalog");
  const th = useTranslations("hub");
  const href = `/catalog/${props.kind === "component" ? "components" : "setups"}/${props.stableId}`;

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
