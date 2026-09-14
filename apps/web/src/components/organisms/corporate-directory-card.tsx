import * as DropdownMenu from "@radix-ui/react-dropdown-menu";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { cn } from "@/lib/cn";
import { Icon, type IconName } from "@/theme";
import { ComponentTypeIcon } from "@/theme/component-types";
import {
  directoryHref,
  isComponentType,
  type DirectoryItem,
  type DirectoryRef,
  type DirectoryResource,
} from "./corporate-directory-types";

type Labels = {
  active: string;
  draft: string;
  archived: string;
  deprecated: string;
  suspended: string;
  lead: string;
  ownerTeam: string;
  teams: string;
  projects: string;
  technologies: string;
  team: string;
  employee: string;
  author: string;
  owner: string;
  type: string;
  moreActions: string;
  unknownEmployee: string;
  notAvailable: string;
};

const resourceIcons: Record<Exclude<DirectoryResource, "components">, IconName> = {
  projects: "component",
  teams: "team",
  members: "user",
  technologies: "technology",
};

function relationHref(ref: DirectoryRef, returnFilters: string) {
  const resource = ref.kind === "employee" ? "members" : ref.kind ? `${ref.kind}s` : "projects";
  return directoryHref(resource as DirectoryResource, ref.id, returnFilters);
}

function EntityMark({ resource, item }: { resource: DirectoryResource; item: DirectoryItem }) {
  if (resource === "components" && isComponentType(item.component_type)) {
    return <ComponentTypeIcon type={item.component_type} compact />;
  }
  const icon = resource === "components" ? "component" : resourceIcons[resource];
  return (
    <span className="bg-muted border-border text-foreground inline-flex size-14 shrink-0 items-center justify-center rounded-md border">
      <Icon name={icon} size="lg" />
    </span>
  );
}

function StatusBadge({ state, labels }: { state: string; labels: Labels }) {
  const label =
    state === "active"
      ? labels.active
      : state === "draft"
        ? labels.draft
        : state === "archived"
          ? labels.archived
          : state === "deprecated"
            ? labels.deprecated
            : labels.suspended;
  return (
    <Badge variant={state === "active" ? "success" : "outline"} className="gap-2 px-3 py-1 text-sm">
      <span
        aria-hidden="true"
        className={cn(
          "size-2 rounded-full",
          state === "active" ? "bg-success-foreground" : "bg-muted-foreground",
        )}
      />
      {label}
    </Badge>
  );
}

function RelationBlock({
  icon,
  label,
  refs,
  labels,
  returnFilters,
}: {
  icon: IconName;
  label: string;
  refs: readonly DirectoryRef[];
  labels: Labels;
  returnFilters: string;
}) {
  return (
    <div className="md:border-border min-w-0 space-y-2 md:border-r md:pr-5 last:md:border-r-0 last:md:pr-0">
      <div className="text-muted-foreground flex items-center gap-2 text-sm">
        <Icon name={icon} size="sm" />
        <span>{label}</span>
      </div>
      {refs.length ? (
        <div className="flex min-w-0 flex-wrap gap-2">
          {refs.map((ref) => (
            <Link
              key={ref.id}
              href={relationHref(ref, returnFilters)}
              className="bg-muted hover:bg-accent hover:text-accent-foreground focus-visible:ring-ring inline-flex max-w-full items-center rounded-md px-3 py-1.5 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              <span className="max-w-full truncate">{ref.name}</span>
            </Link>
          ))}
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">{labels.notAvailable}</p>
      )}
    </div>
  );
}

function ComponentMetadata({ item, labels }: { item: DirectoryItem; labels: Labels }) {
  return (
    <div className="flex min-w-0 flex-wrap gap-2">
      {item.component_type ? <Badge variant="secondary">{item.component_type}</Badge> : null}
      {item.tags?.map((tag) => (
        <Badge key={tag} variant="outline">
          {tag}
        </Badge>
      ))}
      {item.version ? <Badge variant="outline">{item.version}</Badge> : null}
      {item.author_name ? (
        <span className="text-muted-foreground text-sm">
          {labels.author}: <span className="text-foreground">{item.author_name}</span>
        </span>
      ) : null}
      {item.owner_name ? (
        <span className="text-muted-foreground text-sm">
          {labels.owner}: <span className="text-foreground">{item.owner_name}</span>
        </span>
      ) : null}
    </div>
  );
}

function CardRelations({
  resource,
  item,
  labels,
  returnFilters,
}: {
  resource: DirectoryResource;
  item: DirectoryItem;
  labels: Labels;
  returnFilters: string;
}) {
  if (resource === "projects") {
    return (
      <div className="border-border grid min-w-0 gap-5 border-t pt-5 md:grid-cols-3">
        <RelationBlock
          icon="team"
          label={labels.ownerTeam}
          labels={labels}
          refs={item.owner_team ? [item.owner_team] : []}
          returnFilters={returnFilters}
        />
        <RelationBlock
          icon="team"
          label={labels.teams}
          labels={labels}
          refs={item.teams ?? []}
          returnFilters={returnFilters}
        />
        <RelationBlock
          icon="technology"
          label={labels.technologies}
          labels={labels}
          refs={item.technologies ?? []}
          returnFilters={returnFilters}
        />
      </div>
    );
  }
  if (resource === "teams") {
    return (
      <div className="border-border grid min-w-0 gap-5 border-t pt-5 md:grid-cols-3">
        <RelationBlock
          icon="user"
          label={labels.lead}
          labels={labels}
          refs={item.leads ?? []}
          returnFilters={returnFilters}
        />
        <RelationBlock
          icon="component"
          label={labels.projects}
          labels={labels}
          refs={item.projects ?? []}
          returnFilters={returnFilters}
        />
        <RelationBlock
          icon="technology"
          label={labels.technologies}
          labels={labels}
          refs={item.technologies ?? []}
          returnFilters={returnFilters}
        />
      </div>
    );
  }
  if (resource === "members") {
    return (
      <div className="border-border grid min-w-0 gap-5 border-t pt-5 md:grid-cols-3">
        <RelationBlock
          icon="team"
          label={labels.team}
          labels={labels}
          refs={item.teams ?? []}
          returnFilters={returnFilters}
        />
        <RelationBlock
          icon="component"
          label={labels.projects}
          labels={labels}
          refs={item.projects ?? []}
          returnFilters={returnFilters}
        />
        <RelationBlock
          icon="technology"
          label={labels.technologies}
          labels={labels}
          refs={item.technologies ?? []}
          returnFilters={returnFilters}
        />
      </div>
    );
  }
  if (resource === "technologies") {
    return (
      <div className="border-border grid min-w-0 gap-5 border-t pt-5 md:grid-cols-3">
        <RelationBlock
          icon="user"
          label={labels.author}
          labels={labels}
          refs={item.owner ? [item.owner] : []}
          returnFilters={returnFilters}
        />
        <RelationBlock
          icon="component"
          label={labels.projects}
          labels={labels}
          refs={item.projects ?? []}
          returnFilters={returnFilters}
        />
        <RelationBlock
          icon="team"
          label={labels.teams}
          labels={labels}
          refs={item.teams ?? []}
          returnFilters={returnFilters}
        />
      </div>
    );
  }
  return null;
}

export function CorporateDirectoryCard({
  resource,
  item,
  labels,
  returnFilters,
  view,
}: {
  resource: DirectoryResource;
  item: DirectoryItem;
  labels: Labels;
  returnFilters: string;
  view: "list" | "cards";
}) {
  const href = directoryHref(resource, item.id, returnFilters);
  const title = item.name || (resource === "members" ? labels.unknownEmployee : item.name);
  return (
    <li className="min-w-0">
      <article
        className={cn(
          "bg-background border-border group relative min-w-0 overflow-hidden rounded-lg border transition-colors",
          "hover:bg-muted/20 focus-within:ring-ring focus-within:ring-2",
          view === "list" ? "p-4" : "p-5",
        )}
      >
        <div className="flex min-w-0 items-start gap-4 pr-16">
          <EntityMark resource={resource} item={item} />
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h3 className="min-w-0 text-xl leading-tight font-medium tracking-tight break-words">
                <Link
                  href={href}
                  className="hover:text-primary focus-visible:ring-ring rounded-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
                >
                  {title}
                </Link>
              </h3>
              {item.is_lead ? (
                <Badge variant="outline" className="border-primary text-primary">
                  {labels.lead}
                </Badge>
              ) : null}
            </div>
            {resource === "members" && item.role ? (
              <p className="text-muted-foreground mt-1 text-base">{item.role}</p>
            ) : null}
            {item.description ? (
              <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-relaxed break-words">
                {item.description}
              </p>
            ) : null}
            {resource === "components" ? (
              <div className="mt-3">
                <ComponentMetadata item={item} labels={labels} />
              </div>
            ) : null}
          </div>
        </div>
        <div className="absolute top-5 right-5 flex items-center gap-3">
          <StatusBadge state={item.state} labels={labels} />
          <DropdownMenu.Root modal={false}>
            <DropdownMenu.Trigger asChild>
              <Button variant="ghost" size="icon" aria-label={`${labels.moreActions}: ${title}`}>
                <Icon name="moreVertical" size="sm" />
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                sideOffset={4}
                className="border-border bg-popover text-popover-foreground z-50 rounded-lg border p-2 shadow-md"
              >
                <DropdownMenu.Item disabled className="text-muted-foreground px-3 py-2 text-sm">
                  {labels.moreActions}
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
        {resource !== "components" ? (
          <CardRelations
            resource={resource}
            item={item}
            labels={labels}
            returnFilters={returnFilters}
          />
        ) : null}
      </article>
    </li>
  );
}

export type { Labels as CorporateDirectoryCardLabels };
