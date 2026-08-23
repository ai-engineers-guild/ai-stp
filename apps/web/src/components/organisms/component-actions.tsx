"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  createContext,
  useContext,
  useState,
  useSyncExternalStore,
  useTransition,
  type ReactNode,
} from "react";
import { toast } from "sonner";

import { Button } from "@/components/atoms/button";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import { updateCatalogReaction } from "@/lib/actions/catalog-reactions";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme/icons";

export type ObjectActionLabels = {
  copyUrl: string;
  share: string;
  copyId: string;
  copyCli?: string;
  copied: string;
  like: string;
  unlike: string;
  likeMenu?: string;
  unlikeMenu?: string;
  more: string;
  report: string;
  editPresentation?: string;
};

export type ObjectActionProps = {
  stableId: string;
  objectKind?: "component" | "setup";
  sharePath: string;
  likesCount: number;
  initiallyLiked?: boolean;
  labels: ObjectActionLabels;
  reportHref: string | undefined;
  editHref?: string;
  cliCommand?: string;
  canonicalUrl?: string;
};

type LikeState = {
  liked: boolean;
  count: number;
  pending: boolean;
  toggle: () => void;
};

const LikeContext = createContext<LikeState | null>(null);

const itemClassName =
  "hover:bg-muted focus-visible:bg-muted flex min-h-11 w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-sm focus-visible:outline-none";

function useCatalogLike(props: {
  stableId: string;
  objectKind?: "component" | "setup";
  likesCount: number;
  initiallyLiked?: boolean;
  labels: Pick<ObjectActionLabels, "like">;
}): LikeState {
  const [liked, setLiked] = useState(props.initiallyLiked ?? false);
  const [count, setCount] = useState(props.likesCount);
  const [pending, startTransition] = useTransition();
  const objectKind = props.objectKind ?? "component";
  const likeLabel = props.labels.like;
  const stableId = props.stableId;

  function toggle() {
    const next = !liked;
    startTransition(async () => {
      try {
        const state = await updateCatalogReaction(objectKind, stableId, next);
        setLiked(state.liked);
        setCount(state.likes_count);
      } catch {
        toast.error(likeLabel);
      }
    });
  }

  return { liked, count, pending, toggle };
}

function useLikeState(props: {
  stableId: string;
  objectKind?: "component" | "setup";
  likesCount: number;
  initiallyLiked?: boolean;
  labels: Pick<ObjectActionLabels, "like">;
}): LikeState {
  const ctx = useContext(LikeContext);
  const local = useCatalogLike(props);
  return ctx ?? local;
}

export function ObjectLikeProvider({
  children,
  ...props
}: ObjectActionProps & { children: ReactNode }) {
  const like = useCatalogLike(props);
  return <LikeContext.Provider value={like}>{children}</LikeContext.Provider>;
}

export function ObjectLikeControl({
  stableId,
  objectKind = "component",
  likesCount,
  initiallyLiked = false,
  labels,
}: Pick<
  ObjectActionProps,
  "stableId" | "objectKind" | "likesCount" | "initiallyLiked" | "labels"
>) {
  const like = useLikeState({
    stableId,
    objectKind,
    likesCount,
    initiallyLiked,
    labels,
  });

  return (
    <Button
      type="button"
      variant={like.liked ? "default" : "outline"}
      size="sm"
      className="min-h-11"
      aria-pressed={like.liked}
      disabled={like.pending}
      onClick={() => {
        like.toggle();
      }}
    >
      <Icon name="heart" size="sm" fill={like.liked ? "currentColor" : "none"} />
      {like.liked ? labels.unlike : labels.like} · {like.count}
    </Button>
  );
}

export function ObjectOverflowMenu({
  stableId,
  objectKind = "component",
  sharePath,
  likesCount,
  initiallyLiked = false,
  labels,
  reportHref,
  editHref,
  cliCommand,
  canonicalUrl,
}: ObjectActionProps) {
  const [reportOpen, setReportOpen] = useState(false);
  const like = useLikeState({
    stableId,
    objectKind,
    likesCount,
    initiallyLiked,
    labels,
  });
  const likeMenu = labels.likeMenu ?? labels.like;
  const unlikeMenu = labels.unlikeMenu ?? "Unlike";

  // Whether the browser has a share sheet is a fact about the browser, not a
  // state this component transitions through. The server cannot know it, so
  // the server snapshot is `false` and the answer arrives with hydration.
  const supportsNativeShare = useSyncExternalStore(
    () => () => {},
    () => browserShare() !== null,
    () => false,
  );

  async function copy(value: string) {
    await navigator.clipboard.writeText(value);
    toast.success(labels.copied);
  }

  async function share() {
    const url = canonicalUrl ?? new URL(sharePath, location.origin).toString();
    const nativeShare = browserShare();
    if (nativeShare) {
      try {
        await nativeShare({ url });
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
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-11"
            aria-label={labels.more}
          >
            <Icon name="moreVertical" size="sm" />
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={4}
            className="border-border bg-popover z-30 max-w-[min(20rem,calc(100vw-1.5rem))] min-w-52 rounded-lg border p-1 shadow-md"
          >
            <DropdownMenu.Item
              className={itemClassName}
              disabled={like.pending}
              onSelect={() => {
                like.toggle();
              }}
            >
              <Icon name="heart" size="sm" fill={like.liked ? "currentColor" : "none"} />
              {like.liked ? unlikeMenu : likeMenu}
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
                void share();
              }}
            >
              <Icon name="link" size="sm" />
              {supportsNativeShare ? labels.share : labels.copyUrl}
            </DropdownMenu.Item>
            {cliCommand ? (
              <DropdownMenu.Item
                className={itemClassName}
                onSelect={() => {
                  void copy(cliCommand);
                }}
              >
                <Icon name="copy" size="sm" />
                {labels.copyCli ?? "Copy CLI command"}
              </DropdownMenu.Item>
            ) : null}
            {editHref ? (
              <DropdownMenu.Item asChild>
                <Link href={editHref} className={itemClassName}>
                  <Icon name="edit" size="sm" />
                  {labels.editPresentation ?? "Edit bio and media"}
                </Link>
              </DropdownMenu.Item>
            ) : null}
            {reportHref ? (
              <>
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
              </>
            ) : null}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      {reportHref ? (
        <ContactReportDialog
          kind={reportHref.includes("setup") ? "setup" : "component"}
          target={stableId}
          label={labels.report}
          open={reportOpen}
          onOpenChange={setReportOpen}
          hideTrigger
        />
      ) : null}
    </>
  );
}

export function ComponentActions(props: ObjectActionProps) {
  return (
    <ObjectLikeProvider {...props}>
      <div data-ui={UI.component.actions} className="contents">
        <ObjectLikeControl
          stableId={props.stableId}
          objectKind={props.objectKind ?? "component"}
          likesCount={props.likesCount}
          initiallyLiked={props.initiallyLiked ?? false}
          labels={props.labels}
        />
        <div data-ui={UI.component.overflow} className="absolute top-0 right-0">
          <ObjectOverflowMenu {...props} />
        </div>
      </div>
    </ObjectLikeProvider>
  );
}

function browserShare(): ((data?: ShareData) => Promise<void>) | null {
  if (typeof navigator === "undefined") return null;
  const candidate: unknown = Reflect.get(navigator, "share");
  if (typeof candidate !== "function") return null;
  return async (data) => {
    await (Reflect.apply(candidate, navigator, [data]) as Promise<unknown>);
  };
}
