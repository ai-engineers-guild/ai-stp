"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import { toast } from "sonner";

import { EntityActionItems } from "@/components/organisms/entity-action-items";
import type { EntityActionSubject } from "@/lib/api/generated/types.gen";
import { entityActionSubject } from "@/lib/entity-action-subject";
import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import { Link } from "@/lib/i18n/navigation";
import { Icon, type IconName } from "@/theme";

function MenuLink({ href, icon, children }: { href: string; icon: IconName; children: ReactNode }) {
  return (
    <MenuItem asChild>
      <Link href={href}>
        <Icon name={icon} size="sm" />
        {children}
      </Link>
    </MenuItem>
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
    <MenuItem onSelect={onSelect}>
      <Icon name={icon} size="sm" />
      {children}
    </MenuItem>
  );
}

// Canonical order: open, copy ID, copy URL, share, privileged actions, report.
export function EntityDetailMenu({
  moreLabel,
  entityId,
  shareHref,
  copyIdLabel,
  copyUrlLabel,
  shareLabel,
  reportLabel,
  reportTarget,
  subject,
  choices,
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
  subject?: EntityActionSubject;
  choices?: {
    actionId: string;
    label: string;
    icon?: IconName;
    onSelect?: () => void;
    href?: string;
  }[];
}) {
  const actionSubject = subject ?? entityActionSubject(reportTarget);
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
      <Menu modal={false}>
        <MenuTrigger asChild>
          <Button type="button" variant="outline" size="icon" aria-label={moreLabel}>
            <Icon name="more" size="sm" />
          </Button>
        </MenuTrigger>
        <MenuContent sideOffset={6}>
          {actionSubject ? (
            <EntityActionItems
              subject={actionSubject}
              entries={{
                ...Object.fromEntries(
                  (choices ?? []).map((choice) => [
                    choice.actionId,
                    choice.href ? (
                      <MenuLink href={choice.href} icon={choice.icon ?? "eye"}>
                        {choice.label}
                      </MenuLink>
                    ) : (
                      <MenuAction
                        icon={choice.icon ?? "eye"}
                        onSelect={choice.onSelect ?? (() => {})}
                      >
                        {choice.label}
                      </MenuAction>
                    ),
                  ]),
                ),
                copy_id: entityId ? (
                  <MenuAction
                    icon="copy"
                    onSelect={() => {
                      void copy(entityId);
                    }}
                  >
                    {copyIdLabel ?? "Copy ID"}
                  </MenuAction>
                ) : null,
                copy_url: shareHref ? (
                  <MenuAction
                    icon="copy"
                    onSelect={() => {
                      void copy(new URL(shareHref, window.location.origin).toString());
                    }}
                  >
                    {copyUrlLabel ?? "Copy URL"}
                  </MenuAction>
                ) : null,
                share: shareHref ? (
                  <MenuAction
                    icon="link"
                    onSelect={() => {
                      void share();
                    }}
                  >
                    {shareLabel ?? "Share"}
                  </MenuAction>
                ) : null,
                report: reportTarget ? (
                  <MenuAction
                    icon="flag"
                    onSelect={() => {
                      setReportOpen(true);
                    }}
                  >
                    {reportLabel ?? "Report"}
                  </MenuAction>
                ) : null,
              }}
            />
          ) : (
            <MenuItem disabled>{moreLabel}</MenuItem>
          )}
        </MenuContent>
      </Menu>
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
