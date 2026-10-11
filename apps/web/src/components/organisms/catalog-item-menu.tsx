"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { ObjectOverflowMenu } from "@/components/organisms/component-actions";
import { registryCommand } from "@/lib/cli-copy";

type CatalogItemMenuProps = {
  kind: "component" | "setup";
  stableId: string;
  version?: string | null;
  href: string;
  initiallyLiked?: boolean;
  leadingItems?: ReactNode[];
  objectName?: string;
  labels: {
    more: string;
    copyUrl: string;
    copyCli: string;
    copyId: string;
    copied: string;
    report: string;
    like: string;
    unlike: string;
  };
};

export function CatalogItemMenu({
  kind,
  stableId,
  href,
  initiallyLiked = false,
  labels,
  objectName,
}: CatalogItemMenuProps) {
  const catalog = useTranslations("catalog");
  return (
    <ObjectOverflowMenu
      stableId={stableId}
      objectKind={kind}
      sharePath={href}
      likesCount={0}
      initiallyLiked={initiallyLiked}
      reportHref={href}
      openHref={href}
      cliCommand={registryCommand(stableId)}
      {...(objectName ? { objectName } : {})}
      labels={{ ...labels, share: catalog("share") }}
    />
  );
}
