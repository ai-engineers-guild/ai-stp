"use client";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { toast } from "sonner";
import { Button } from "@/components/atoms/button";
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
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <Button type="button" variant="outline" size="icon" aria-label={labels.more}>
          <Icon name="more" size="sm" />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          side="bottom"
          align="end"
          sideOffset={4}
          collisionPadding={12}
          className="border-border bg-popover text-popover-foreground z-[80] min-w-56 rounded-lg border p-1 shadow-md"
        >
          <DropdownMenu.Item
            className="hover:bg-muted focus:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
            onSelect={() => void copy(window.location.href)}
          >
            <Icon name="link" size="sm" /> {labels.copyLink}
          </DropdownMenu.Item>
          <DropdownMenu.Item
            className="hover:bg-muted focus:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
            onSelect={() => void copy(accountId)}
          >
            <Icon name="copy" size="sm" /> {labels.copyId}
          </DropdownMenu.Item>
          {cliCommand ? (
            <DropdownMenu.Item
              className="hover:bg-muted focus:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
              onSelect={() => void copy(cliCommand)}
            >
              <Icon name="copy" size="sm" /> {labels.useCli}
            </DropdownMenu.Item>
          ) : null}
          {editHref && labels.editProfile ? (
            <DropdownMenu.Item
              className="hover:bg-muted focus:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
              onSelect={() => {
                router.push(editHref);
              }}
            >
              <Icon name="edit" size="sm" /> {labels.editProfile}
            </DropdownMenu.Item>
          ) : null}
          <DropdownMenu.Separator className="border-border my-1 border-t" />
          <DropdownMenu.Item
            className="hover:bg-muted focus:bg-muted flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm outline-none"
            onSelect={() => {
              router.push(reportHref);
            }}
          >
            <Icon name="flag" size="sm" /> {labels.report}
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
