"use client";
import { toast } from "sonner";
import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from "@/components/atoms/menu";
import { useRouter } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
export function PublisherActions({
  accountId,
  reportHref,
  cliCommand,
  editHref,
  labels,
}: {
  accountId: string;
  reportHref: string;
  cliCommand: string | null;
  editHref?: string;
  labels: {
    more: string;
    report: string;
    copyLink: string;
    copyId: string;
    useCli: string;
    editProfile?: string;
    copied: string;
  };
}) {
  const router = useRouter();
  async function copy(value: string) {
    await navigator.clipboard.writeText(value);
    toast.success(labels.copied);
  }
  return (
    <Menu modal={false}>
      <MenuTrigger asChild>
        <Button type="button" variant="outline" size="icon" aria-label={labels.more}>
          <Icon name="more" size="sm" />
        </Button>
      </MenuTrigger>
      <MenuContent>
        <MenuItem onSelect={() => void copy(window.location.href)}>
          <Icon name="link" size="sm" /> {labels.copyLink}
        </MenuItem>
        <MenuItem onSelect={() => void copy(accountId)}>
          <Icon name="copy" size="sm" /> {labels.copyId}
        </MenuItem>
        {cliCommand ? (
          <MenuItem onSelect={() => void copy(cliCommand)}>
            <Icon name="copy" size="sm" /> {labels.useCli}
          </MenuItem>
        ) : null}
        {editHref && labels.editProfile ? (
          <MenuItem
            onSelect={() => {
              router.push(editHref);
            }}
          >
            <Icon name="edit" size="sm" /> {labels.editProfile}
          </MenuItem>
        ) : null}
        <MenuSeparator />
        <MenuItem
          onSelect={() => {
            router.push(reportHref);
          }}
        >
          <Icon name="flag" size="sm" /> {labels.report}
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}
