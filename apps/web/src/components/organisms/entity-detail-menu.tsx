"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/atoms/button";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

export function EntityDetailMenu({
  moreLabel,
  openLabel,
  openHref,
  editLabel,
  editHref,
  editPresentationLabel,
  editPresentationHref,
  entityId,
  shareHref,
  copyIdLabel,
  shareLabel,
  reportLabel,
  reportTarget,
}: {
  moreLabel: string;
  openLabel?: string | undefined;
  openHref?: string | undefined;
  editLabel?: string | undefined;
  editHref?: string | undefined;
  editPresentationLabel?: string | undefined;
  editPresentationHref?: string | undefined;
  entityId?: string | undefined;
  shareHref?: string | undefined;
  copyIdLabel?: string | undefined;
  shareLabel?: string | undefined;
  reportLabel?: string | undefined;
  reportTarget?: string | undefined;
}) {
  const [reportOpen, setReportOpen] = useState(false);

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(copyIdLabel ?? "Copied");
    } catch {
      toast.error(copyIdLabel ?? "Copy failed");
    }
  }

  async function share() {
    if (!shareHref) return;
    const url = new URL(shareHref, window.location.origin).toString();
    const nativeShare = Reflect.get(navigator, "share");
    if (typeof nativeShare === "function") {
      try {
        await Reflect.apply(nativeShare, navigator, [{ url }]);
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
      }
    }
    await copy(url);
  }

  return (
    <>
      <DropdownMenu.Root modal={false}>
        <DropdownMenu.Trigger asChild>
          <Button type="button" variant="outline" size="icon" aria-label={moreLabel}>
            <Icon name="more" size="sm" />
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={6}
            className="border-border bg-popover text-popover-foreground z-50 min-w-48 rounded-md border p-1 shadow-md"
          >
            {openHref ? (
              <DropdownMenu.Item asChild>
                <Link
                  href={openHref}
                  className="hover:bg-muted focus-visible:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
                >
                  <Icon name="eye" size="sm" />
                  {openLabel ?? "Open details"}
                </Link>
              </DropdownMenu.Item>
            ) : null}
            {editHref ? (
              <DropdownMenu.Item asChild>
                <Link
                  href={editHref}
                  className="hover:bg-muted focus-visible:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
                >
                  <Icon name="edit" size="sm" />
                  {editLabel}
                </Link>
              </DropdownMenu.Item>
            ) : null}
            {editPresentationHref ? (
              <DropdownMenu.Item asChild>
                <Link
                  href={editPresentationHref}
                  className="hover:bg-muted focus-visible:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
                >
                  <Icon name="edit" size="sm" />
                  {editPresentationLabel}
                </Link>
              </DropdownMenu.Item>
            ) : null}
            {entityId ? (
              <DropdownMenu.Item
                className="hover:bg-muted focus-visible:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
                onSelect={() => {
                  void copy(entityId);
                }}
              >
                <Icon name="copy" size="sm" />
                {copyIdLabel ?? "Copy ID"}
              </DropdownMenu.Item>
            ) : null}
            {shareHref ? (
              <DropdownMenu.Item
                className="hover:bg-muted focus-visible:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
                onSelect={() => {
                  void share();
                }}
              >
                <Icon name="link" size="sm" />
                {shareLabel ?? "Share"}
              </DropdownMenu.Item>
            ) : null}
            {reportTarget ? (
              <DropdownMenu.Item
                className="hover:bg-muted focus-visible:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
                onSelect={() => {
                  setReportOpen(true);
                }}
              >
                <Icon name="flag" size="sm" />
                {reportLabel ?? "Report"}
              </DropdownMenu.Item>
            ) : null}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      {reportTarget ? (
        <ContactReportDialog
          kind="entity"
          target={reportTarget}
          label={reportLabel ?? "Report"}
          open={reportOpen}
          onOpenChange={setReportOpen}
          hideTrigger
        />
      ) : null}
    </>
  );
}
