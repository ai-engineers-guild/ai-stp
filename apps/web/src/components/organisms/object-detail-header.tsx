import type { ReactNode } from "react";

import {
  ObjectLikeControl,
  ObjectOverflowMenu,
  type ObjectActionProps,
} from "@/components/organisms/component-actions";
import type { GitSource } from "@/lib/api/generated/types.gen";
import { githubSourceUrl } from "@/lib/source-url";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme/icons";

export function ObjectDetailHeader({
  icon,
  title,
  badges,
  versionLabel,
  githubStars,
  githubStarsLabel,
  archived,
  archivedLabel,
  source,
  viewSourceLabel,
  like,
  actions,
}: {
  icon: ReactNode;
  title: string;
  badges: ReactNode;
  versionLabel: string;
  githubStars: number | null | undefined;
  githubStarsLabel: string;
  archived?: boolean | null;
  archivedLabel: string;
  source: GitSource | null | undefined;
  viewSourceLabel: string;
  like: ObjectActionProps;
  actions?: ReactNode;
}) {
  const sourceHref = githubSourceUrl(source ?? null);

  return (
    <header
      data-ui={UI.component.detailHeader}
      className="border-border relative min-w-0 overflow-x-clip border-b pb-8"
    >
      <div data-ui={UI.component.overflow} className="absolute top-0 right-0 z-10">
        <ObjectOverflowMenu {...like} />
      </div>
      <div className="flex min-w-0 items-start gap-3 pr-12 sm:gap-4">
        <div className="shrink-0">{icon}</div>
        <div className="min-w-0 flex-1 space-y-3">
          <h1 className="text-2xl font-semibold tracking-tight break-words sm:text-3xl lg:text-4xl">
            {title}
          </h1>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            {badges}
            <span className="text-muted-foreground text-sm">{versionLabel}</span>
          </div>
          <div
            data-ui={UI.component.actions}
            className="flex min-w-0 flex-wrap items-center gap-2 lg:absolute lg:right-12 lg:bottom-8 lg:justify-end"
          >
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
            {sourceHref ? (
              <span className="inline-flex min-w-0 flex-wrap items-center gap-2">
                <a
                  href={sourceHref}
                  target="_blank"
                  rel="noreferrer"
                  className="focus-visible:ring-ring inline-flex min-h-11 min-w-0 items-center gap-1.5 text-sm font-medium break-words underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
                >
                  <Icon name="github" size="sm" />
                  {viewSourceLabel}
                </a>
                {archived === true ? (
                  <span className="border-border bg-muted inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium">
                    {archivedLabel}
                  </span>
                ) : null}
              </span>
            ) : null}
            {actions}
          </div>
        </div>
      </div>
    </header>
  );
}
