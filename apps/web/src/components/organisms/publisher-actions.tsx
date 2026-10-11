"use client";
import { toast } from "sonner";
import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";
import { EntityActionItems } from "@/components/organisms/entity-action-items";
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
        <EntityActionItems
          subject={{ kind: "publisher", id: accountId }}
          entries={{
            copy_url: (
              <MenuItem
                onSelect={() => {
                  void copy(window.location.href);
                }}
              >
                <Icon name="link" size="sm" />
                {labels.copyLink}
              </MenuItem>
            ),
            copy_id: (
              <MenuItem
                onSelect={() => {
                  void copy(accountId);
                }}
              >
                <Icon name="copy" size="sm" />
                {labels.copyId}
              </MenuItem>
            ),
            copy_cli: (
              <MenuItem
                disabled={!cliCommand}
                onSelect={() => {
                  if (cliCommand) void copy(cliCommand);
                }}
              >
                <Icon name="copy" size="sm" />
                {labels.useCli}
              </MenuItem>
            ),
            edit_profile: (
              <MenuItem
                onSelect={() => {
                  router.push(editHref ?? "/account/profile/edit");
                }}
              >
                <Icon name="edit" size="sm" />
                {labels.editProfile}
              </MenuItem>
            ),
            report: (
              <MenuItem
                onSelect={() => {
                  router.push(reportHref);
                }}
              >
                <Icon name="flag" size="sm" />
                {labels.report}
              </MenuItem>
            ),
          }}
        />
      </MenuContent>
    </Menu>
  );
}
