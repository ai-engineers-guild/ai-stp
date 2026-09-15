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
  const icon = resource === "components" ? "component" : resourceIcons[resource];
  return (
    <span className="bg-muted border-border text-foreground inline-flex size-14 shrink-0 items-center justify-center rounded-md border">
      {resource === "components" && isComponentType(item.component_type) ? (
        <ComponentTypeIcon type={item.component_type} compact />
      ) : (
        <Icon name={icon} size="lg" />
      )}
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

function ReferenceChip({
  reference,
  returnFilters,
}: {
  reference: DirectoryRef;
  returnFilters: string;
}) {
  return (
    <Link
      href={relationHref(reference, returnFilters)}
      className="bg-muted hover:bg-accent hover:text-accent-foreground focus-visible:ring-ring inline-flex max-w-full items-center rounded-md px-3 py-1.5 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
    >
      <span className="max-w-full truncate">{reference.name}</span>
    </Link>
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

function primaryReferences(resource: DirectoryResource, item: DirectoryItem) {
  if (resource === "projects" || resource === "teams") return item.technologies ?? [];
  if (resource === "members") return item.teams ?? [];
  return [];
}

function RelationColumn({
  icon,
  label,
  references,
  returnFilters,
}: {
  icon: IconName;
  label: string;
  references: readonly DirectoryRef[];
  returnFilters: string;
}) {
  return (
    <div className="border-border min-w-0 space-y-1 border-l pl-4 first:border-l-0 first:pl-0">
      <div className="text-muted-foreground flex items-center gap-2 text-sm">
        <Icon name={icon} size="sm" />
        <span>{label}</span>
      </div>
      <div className="flex min-w-0 flex-wrap gap-2">
        {references.length ? (
          references.map((reference) => (
            <ReferenceChip key={reference.id} reference={reference} returnFilters={returnFilters} />
          ))
        ) : (
          <span className="text-muted-foreground text-sm">—</span>
        )}
      </div>
    </div>
  );
}

function footerReferences(resource: DirectoryResource, item: DirectoryItem) {
  if (resource === "projects") {
    return {
      label: "ownerTeam",
      icon: "team" as IconName,
      refs: item.owner_team ? [item.owner_team] : [],
    };
  }
  if (resource === "teams") {
    return { label: "lead", icon: "user" as IconName, refs: item.leads ?? [] };
  }
  return null;
}

function CardFooter({
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
  const footer = footerReferences(resource, item);
  if (!footer) return null;
  return (
    <div className="border-border mt-5 flex min-w-0 flex-wrap items-center justify-between gap-3 border-t pt-4">
      <div className="text-muted-foreground flex min-w-0 items-center gap-2 text-sm">
        <Icon name={footer.icon} size="sm" />
        <span>{labels[footer.label as keyof Labels]}</span>
      </div>
      <div className="flex min-w-0 flex-wrap justify-end gap-2">
        {footer.refs.length ? (
          footer.refs.map((reference) => (
            <ReferenceChip key={reference.id} reference={reference} returnFilters={returnFilters} />
          ))
        ) : (
          <span className="text-muted-foreground text-sm">{labels.notAvailable}</span>
        )}
      </div>
    </div>
  );
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
  const references = primaryReferences(resource, item);
  const technologyRelations =
    resource === "technologies" ? (
      <div className="border-border mt-5 grid min-w-0 gap-4 border-t pt-4 sm:grid-cols-3">
        <RelationColumn
          icon="user"
          label={labels.owner}
          references={item.owner ? [item.owner] : []}
          returnFilters={returnFilters}
        />
        <RelationColumn
          icon="component"
          label={labels.projects}
          references={item.projects ?? []}
          returnFilters={returnFilters}
        />
        <RelationColumn
          icon="team"
          label={labels.teams}
          references={item.teams ?? []}
          returnFilters={returnFilters}
        />
      </div>
    ) : null;
  return (
    <li className="min-w-0">
      <article
        className={cn(
          "bg-background border-border group relative min-w-0 overflow-hidden rounded-lg border transition-colors",
          "hover:bg-muted/20 focus-within:ring-ring focus-within:ring-2",
          view === "list" ? "p-4" : "p-5",
        )}
      >
        <div className="flex min-w-0 items-start gap-4 pr-20">
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
            {references.length ? (
              <div className="mt-4 flex min-w-0 flex-wrap gap-2">
                {references.map((reference) => (
                  <ReferenceChip
                    key={reference.id}
                    reference={reference}
                    returnFilters={returnFilters}
                  />
                ))}
              </div>
            ) : null}
            {item.description ? (
              <p className="text-muted-foreground mt-4 max-w-3xl text-sm leading-relaxed break-words">
                {item.description}
              </p>
            ) : null}
            {resource === "components" ? (
              <div className="mt-4">
                <ComponentMetadata item={item} labels={labels} />
              </div>
            ) : null}
            {technologyRelations}
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
        <CardFooter resource={resource} item={item} labels={labels} returnFilters={returnFilters} />
      </article>
    </li>
  );
}

export type { Labels as CorporateDirectoryCardLabels };
