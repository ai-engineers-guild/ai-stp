"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/atoms/button";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import { registryCommand } from "@/lib/cli-copy";
import { buildDeepLink, normalizeTarget } from "@/lib/deep-links";
import { Icon } from "@/theme";

type CatalogItemMenuProps = {
  kind: "component" | "setup";
  stableId: string;
  version: string;
  href: string;
  labels: {
    more: string;
    copyUrl: string;
    copyCli: string;
    copyId: string;
    copied: string;
    report: string;
  };
};

const itemClassName =
  "hover:bg-muted focus:bg-muted flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-sm outline-none";

export function CatalogItemMenu({ kind, stableId, version, href, labels }: CatalogItemMenuProps) {
  const [reportOpen, setReportOpen] = useState(false);
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
        normalizeTarget({ kind, stable_id: stableId, version, locale }),
      ).web_url;
    } catch {
      const prefix = localeMatch?.[0] ?? "";
      return `${window.location.origin}${prefix}${href}`;
    }
  }

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-11 w-11"
            aria-label={labels.more}
          >
            <Icon name="more" size="sm" />
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            side="bottom"
            align="end"
            sideOffset={4}
            collisionPadding={12}
            className="border-border bg-popover text-popover-foreground z-[80] max-w-[calc(100vw-1.5rem)] min-w-56 rounded-lg border p-1 shadow-md"
          >
            <DropdownMenu.Item
              className={itemClassName}
              onSelect={() => {
                void copy(publicUrl());
              }}
            >
              <Icon name="link" size="sm" />
              {labels.copyUrl}
            </DropdownMenu.Item>
            <DropdownMenu.Item
              className={itemClassName}
              onSelect={() => {
                void copy(stableId);
              }}
            >
              <Icon name="copy" size="sm" />
              {labels.copyId}
            </DropdownMenu.Item>
            <DropdownMenu.Item
              className={itemClassName}
              onSelect={() => {
                void copy(cliCommand);
              }}
            >
              <Icon name="copy" size="sm" />
              {labels.copyCli}
            </DropdownMenu.Item>
            <DropdownMenu.Separator className="border-border my-1 border-t" />
            <DropdownMenu.Item
              className={itemClassName}
              onSelect={() => {
                setReportOpen(true);
              }}
            >
              <Icon name="flag" size="sm" />
              {labels.report}
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <ContactReportDialog
        kind={kind}
        target={`${stableId}@${version}`}
        label={labels.report}
        hideTrigger
        open={reportOpen}
        onOpenChange={setReportOpen}
      />
    </>
  );
}
