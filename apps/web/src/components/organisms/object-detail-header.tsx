import type { ReactNode } from "react";

import {
  ObjectLikeControl,
  ObjectLikeProvider,
  ObjectOverflowMenu,
  type ObjectActionProps,
} from "@/components/organisms/component-actions";
import type { GitSource } from "@/lib/api/generated/types.gen";
import { sourceLinksFor, type PublicSourceLink } from "@/lib/source-url";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme/icons";
import { VisibilityLabel } from "@/components/molecules/visibility-label";
import { EntityDetailHeader } from "@/components/organisms/entity-detail-header";

export function ObjectDetailHeader({
  icon,
  title,
  badges,
  githubStars,
  githubStarsLabel,
  archived,
  archivedLabel,
  source,
  sourceLinks,
  viewSourceLabel,
  like,
  actions,
  visibility,
  publicVisibilityLabel,
  privateVisibilityLabel,
}: {
  icon: ReactNode;
  title: string;
  badges: ReactNode;
  githubStars: number | null | undefined;
  githubStarsLabel: string;
  archived?: boolean | null;
  archivedLabel: string;
  source: GitSource | null | undefined;
  sourceLinks?: readonly (PublicSourceLink & { label: string })[];
  viewSourceLabel: string;
  like: ObjectActionProps;
  actions?: ReactNode;
  visibility?: "public" | "private";
  publicVisibilityLabel?: string;
  privateVisibilityLabel?: string;
}) {
  const links =
    sourceLinks ??
    sourceLinksFor(source ?? null).map((item) => ({ ...item, label: viewSourceLabel }));

  return (
    <ObjectLikeProvider {...like}>
      <EntityDetailHeader
        icon={icon}
        title={title}
        meta={badges}
        menu={
          <div className="flex items-center gap-2">
            {visibility ? (
              <VisibilityLabel
                visibility={visibility}
                publicLabel={publicVisibilityLabel}
                privateLabel={privateVisibilityLabel}
              />
            ) : null}
            <div data-ui={UI.component.overflow}>
              <ObjectOverflowMenu {...like} />
            </div>
          </div>
        }
        stats={
          <>
            <ObjectLikeControl
              stableId={like.stableId}
              objectKind={like.objectKind ?? "component"}
              likesCount={like.likesCount}
              initiallyLiked={like.initiallyLiked ?? false}
              labels={like.labels}
            />
            {githubStars !== null && githubStars !== undefined ? (
              <span
                className="border-border inline-flex min-h-11 items-center gap-1.5 rounded-md border px-2 py-1 text-sm"
                aria-label={`${githubStarsLabel}: ${githubStars}`}
              >
                <Icon name="star" size="sm" />
                <span className="font-mono tabular-nums">{githubStars}</span>
                <span className="text-muted-foreground">{githubStarsLabel}</span>
              </span>
            ) : null}
            {links.length ? (
              <span className="inline-flex min-w-0 flex-wrap items-center gap-2">
                {links.map((item) => (
                  <a
                    key={item.href}
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-visible:ring-ring inline-flex min-h-11 min-w-0 items-center gap-1.5 text-sm font-medium break-words underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
                  >
                    <Icon name={item.provider === "GitHub" ? "github" : "link"} size="sm" />
                    {item.label}
                  </a>
                ))}
                {archived === true ? (
                  <span className="border-border bg-muted inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium">
                    {archivedLabel}
                  </span>
                ) : null}
              </span>
            ) : null}
            {actions}
          </>
        }
      />
    </ObjectLikeProvider>
  );
}
