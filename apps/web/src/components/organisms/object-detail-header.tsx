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
  sourceLinks,
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
  sourceLinks?: readonly (PublicSourceLink & { label: string })[];
  viewSourceLabel: string;
  like: ObjectActionProps;
  actions?: ReactNode;
}) {
  const links =
    sourceLinks ??
    sourceLinksFor(source ?? null).map((item) => ({ ...item, label: viewSourceLabel }));

  return (
    <ObjectLikeProvider {...like}>
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
            <h1 className="max-w-4xl text-xl leading-tight font-semibold tracking-tight [overflow-wrap:anywhere] break-words sm:text-2xl lg:text-3xl">
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
            </div>
          </div>
        </div>
      </header>
    </ObjectLikeProvider>
  );
}
