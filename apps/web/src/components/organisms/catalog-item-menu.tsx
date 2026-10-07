"use client";

import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { corporateAssignContextAction, type CorporateAssignContext } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/atoms/menu";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import { CorporateAssignDialog } from "@/components/organisms/corporate-assign-dialog";
import { useCatalogLike } from "@/components/organisms/use-catalog-like";
import { registryCommand } from "@/lib/cli-copy";
import { buildDeepLink, normalizeTarget } from "@/lib/deep-links";
import { Icon } from "@/theme";

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
  version,
  href,
  initiallyLiked = false,
  leadingItems,
  labels,
  objectName,
}: CatalogItemMenuProps) {
  const [reportOpen, setReportOpen] = useState(false);
  const [assignCtx, setAssignCtx] = useState<CorporateAssignContext | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);
  const like = useCatalogLike({ stableId, objectKind: kind, initiallyLiked, labels });
  const cliCommand = registryCommand(stableId);

  async function copy(value: string) {
    await navigator.clipboard.writeText(value);
    toast.success(labels.copied);
  }

  function publicUrl(): string {
    const localeMatch = window.location.pathname.match(/^\/(en|ru)(?=\/|$)/);
    const locale = localeMatch?.[1] === "en" ? "en" : "ru";
    try {
      return buildDeepLink(
        window.location.origin,
        normalizeTarget({ kind, stable_id: stableId, version: version ?? "", locale }),
      ).web_url;
    } catch {
      const prefix = localeMatch?.[0] ?? "";
      return `${window.location.origin}${prefix}${href}`;
    }
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
            className="border-border bg-card/80 hover:bg-muted h-11 w-11 border shadow-sm transition-shadow hover:shadow-md focus-visible:ring-2"
            aria-label={labels.more}
          >
            <Icon name="more" size="sm" />
          </Button>
        </MenuTrigger>
        <MenuContent>
          {leadingItems}
          {leadingItems?.length ? <MenuSeparator /> : null}
          <MenuItem
            onSelect={() => {
              void copy(publicUrl());
            }}
          >
            <Icon name="link" size="sm" />
            {labels.copyUrl}
          </MenuItem>
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
              void copy(cliCommand);
            }}
          >
            <Icon name="copy" size="sm" />
            {labels.copyCli}
          </MenuItem>
          <MenuSeparator />
          <MenuItem
            disabled={like.pending}
            onSelect={() => {
              like.toggle();
            }}
          >
            <Icon name="heart" size="sm" fill={like.liked ? "currentColor" : "none"} />
            {like.liked ? labels.unlike : labels.like}
          </MenuItem>
          {assignCtx?.ok ? (
            <MenuItem
              onSelect={() => {
                setAssignOpen(true);
              }}
            >
              <Icon name="team" size="sm" />
              {assignCtx.labels.assign}
            </MenuItem>
          ) : null}
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
          objectKind={kind}
          stableId={stableId}
          objectName={objectName ?? stableId}
        />
      ) : null}
      <ContactReportDialog
        kind={kind}
        target={`${stableId}${version ? `@${version}` : ""}`}
        label={labels.report}
        hideTrigger
        open={reportOpen}
        onOpenChange={setReportOpen}
      />
    </>
  );
}
