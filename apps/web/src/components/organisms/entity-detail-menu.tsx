"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import type { ReactNode } from "react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/atoms/button";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import { Link } from "@/lib/i18n/navigation";
import { Icon, type IconName } from "@/theme";

const itemClassName =
  "hover:bg-muted focus-visible:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none";

function MenuLink({ href, icon, children }: { href: string; icon: IconName; children: ReactNode }) {
  return (
    <DropdownMenu.Item asChild>
      <Link href={href} className={itemClassName}>
        <Icon name={icon} size="sm" />
        {children}
      </Link>
    </DropdownMenu.Item>
  );
}

function MenuAction({
  icon,
  onSelect,
  children,
}: {
  icon: IconName;
  onSelect: () => void;
  children: ReactNode;
}) {
  return (
    <DropdownMenu.Item className={itemClassName} onSelect={onSelect}>
      <Icon name={icon} size="sm" />
      {children}
    </DropdownMenu.Item>
  );
}

// Canonical order: open, copy ID, copy URL, share, privileged actions, report.
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
  copyUrlLabel,
  shareLabel,
  reportLabel,
  reportTarget,
  adminItems,
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
  copyUrlLabel?: string | undefined;
  shareLabel?: string | undefined;
  reportLabel?: string | undefined;
  reportTarget?: string | undefined;
  adminItems?: ReactNode;
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
              <MenuLink href={openHref} icon="eye">
                {openLabel ?? "Open details"}
              </MenuLink>
            ) : null}
            {entityId ? (
              <MenuAction
                icon="copy"
                onSelect={() => {
                  void copy(entityId);
                }}
              >
                {copyIdLabel ?? "Copy ID"}
              </MenuAction>
            ) : null}
            {shareHref ? (
              <MenuAction
                icon="copy"
                onSelect={() => {
                  void copy(new URL(shareHref, window.location.origin).toString());
                }}
              >
                {copyUrlLabel ?? "Copy URL"}
              </MenuAction>
            ) : null}
            {shareHref ? (
              <MenuAction
                icon="link"
                onSelect={() => {
                  void share();
                }}
              >
                {shareLabel ?? "Share"}
              </MenuAction>
            ) : null}
            {editHref ? (
              <MenuLink href={editHref} icon="edit">
                {editLabel}
              </MenuLink>
            ) : null}
            {editPresentationHref ? (
              <MenuLink href={editPresentationHref} icon="edit">
                {editPresentationLabel}
              </MenuLink>
            ) : null}
            {adminItems}
            {reportTarget ? (
              <MenuAction
                icon="flag"
                onSelect={() => {
                  setReportOpen(true);
                }}
              >
                {reportLabel ?? "Report"}
              </MenuAction>
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
