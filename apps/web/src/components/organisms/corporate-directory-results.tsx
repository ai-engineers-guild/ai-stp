"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
import type { CorporateDirectoryReference } from "@/lib/api/generated/types.gen";

type Ref = Pick<CorporateDirectoryReference, "id" | "name">;
export type DirectoryItem = {
  id: string;
  name: string;
  state: string;
  description?: string;
  role?: string | null;
  leads?: readonly Ref[];
  teams?: readonly Ref[];
  related_teams?: readonly Ref[];
  projects?: readonly Ref[];
  technologies?: readonly Ref[];
  owner_team?: Ref | null;
  owner?: Ref | null;
  categories?: readonly Ref[];
  is_lead?: boolean;
};
export type DirectoryResource = "teams" | "projects" | "technologies" | "members";
type Facet = "leads" | "teams" | "technologies" | "projects" | "categories";

const facets: Record<DirectoryResource, Facet[]> = {
  teams: ["leads", "technologies", "teams"],
  projects: ["teams", "technologies"],
  technologies: ["projects", "teams", "categories"],
  members: ["projects", "teams", "technologies"],
};

const facetParams: Record<Facet, string> = {
  leads: "lead_ids",
  teams: "team_ids",
  technologies: "technology_ids",
  projects: "project_ids",
  categories: "category_ids",
};

function references(item: DirectoryItem, facet: Facet): readonly Ref[] {
  if (facet === "teams")
    return [
      ...(item.teams ?? []),
      ...(item.related_teams ?? []),
      ...(item.owner_team ? [item.owner_team] : []),
    ];
  return item[facet] ?? [];
}

function currentReturnFilters(seed: string): string {
  const current = new URLSearchParams(window.location.search);
  const initial = new URLSearchParams(seed);
  for (const [key, value] of initial) {
    if (!current.has(key)) current.append(key, value);
  }
  return current.toString();
}

export function matchesDirectoryFilters(
  item: DirectoryItem,
  selected: Partial<Record<Facet, string[]>>,
) {
  return Object.entries(selected).every(
    ([facet, values]) =>
      !values.length || references(item, facet as Facet).some((ref) => values.includes(ref.id)),
  );
}

// eslint-disable-next-line max-lines-per-function
export function CorporateDirectoryResults({
  resource,
  items,
  filters = "",
}: {
  resource: DirectoryResource;
  items: readonly DirectoryItem[];
  filters?: string;
}) {
  const t = useTranslations("hub");
  const catalog = useTranslations("catalog");
  const [view, setView] = useState<"list" | "cards">("cards");
  const [selected, setSelected] = useState<Partial<Record<Facet, string[]>>>({});
  const [leadOnly, setLeadOnly] = useState(false);
  const [returnFilters, setReturnFilters] = useState(filters);
  const [filterRevision, setFilterRevision] = useState(0);
  useEffect(() => {
    function restore() {
      const params = new URLSearchParams(window.location.search);
      setView(params.get("view") === "list" ? "list" : "cards");
      setSelected(
        Object.fromEntries(
          facets[resource].map((facet) => [facet, params.getAll(facetParams[facet])]),
        ),
      );
      setLeadOnly(params.get("is_lead") === "true");
      setReturnFilters(currentReturnFilters(filters));
      setFilterRevision((revision) => revision + 1);
    }
    restore();
    window.addEventListener("popstate", restore);
    return () => {
      window.removeEventListener("popstate", restore);
    };
  }, [filters, resource]);
  function persist(name: string, values: string[]) {
    const url = new URL(window.location.href);
    url.searchParams.delete(name);
    values.forEach((value) => {
      url.searchParams.append(name, value);
    });
    window.history.replaceState(window.history.state, "", url);
    setReturnFilters(url.searchParams.toString());
  }
  const visible = items.filter(
    (item) => matchesDirectoryFilters(item, selected) && (!leadOnly || item.is_lead),
  );
  return (
    <section className="min-w-0 space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {facets[resource].map((facet) => (
            <SearchableMultiSelect
              key={`${facet}:${filterRevision}`}
              name={`directory-${facet}`}
              label={t(facet === "leads" ? "teamLeads" : facet)}
              searchLabel={`${t("search")}: ${t(facet === "leads" ? "teamLeads" : facet)}`}
              options={[
                ...new Map(
                  items
                    .flatMap((item) => references(item, facet))
                    .map((ref) => [ref.id, { value: ref.id, label: ref.name }]),
                ).values(),
              ]}
              selected={selected[facet] ?? []}
              onChange={(values) => {
                setSelected((previous) => ({ ...previous, [facet]: values }));
                persist(facetParams[facet], values);
              }}
            />
          ))}
        </div>
        <div className="flex gap-2">
          {(["list", "cards"] as const).map((mode) => (
            <Button
              key={mode}
              variant="outline"
              size="icon"
              aria-label={catalog(mode === "list" ? "listView" : "cardsView")}
              aria-pressed={view === mode}
              onClick={() => {
                setView(mode);
                persist("view", [mode]);
              }}
            >
              <Icon name={mode} size="sm" />
            </Button>
          ))}
        </div>
      </div>
      {resource === "members" && (
        <label className="flex min-h-11 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={leadOnly}
            onChange={(event) => {
              setLeadOnly(event.target.checked);
              persist("is_lead", event.target.checked ? ["true"] : []);
            }}
          />
          {t("lead")}
        </label>
      )}
      <p aria-live="polite" className="text-muted-foreground text-right font-mono text-sm">
        {visible.length}
      </p>
      <ul
        className={
          view === "cards"
            ? "grid min-w-0 gap-3 md:grid-cols-2"
            : "border-border divide-border grid min-w-0 divide-y overflow-hidden rounded-lg border"
        }
      >
        {visible.map((item) => {
          const tags =
            resource === "members"
              ? item.teams
              : resource === "technologies"
                ? item.projects
                : item.technologies;
          const owners =
            resource === "teams"
              ? item.leads
              : resource === "projects"
                ? item.owner_team
                  ? [item.owner_team]
                  : []
                : resource === "technologies"
                  ? item.owner
                    ? [item.owner]
                    : []
                  : [];
          return (
            <li
              key={item.id}
              className={`bg-card relative min-w-0 ${view === "cards" ? "border-border rounded-lg border" : ""}`}
            >
              <Link
                href={`/corporate/${resource}/${encodeURIComponent(item.id)}${returnFilters ? `?${returnFilters}` : ""}`}
                className="hover:bg-muted/50 focus-visible:ring-ring flex h-full min-w-0 flex-col gap-4 rounded-lg p-5 focus-visible:ring-2 focus-visible:outline-none"
              >
                <div className="flex min-w-0 items-start gap-3 pr-12">
                  <span className="border-border grid size-11 shrink-0 place-items-center rounded-sm border">
                    <Icon name={resource === "members" ? "user" : "controls"} />
                  </span>
                  <h3 className="min-w-0 text-xl font-medium tracking-tight break-words">
                    {item.name || (resource === "members" ? t("unknownEmployee") : item.name)}
                  </h3>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {tags?.map((tag) => (
                    <Badge key={tag.id} variant="outline">
                      {tag.name}
                    </Badge>
                  ))}
                  {item.is_lead && <Badge variant="secondary">{t("lead")}</Badge>}
                </div>
                {item.description && (
                  <p className="text-muted-foreground line-clamp-3 text-sm leading-relaxed break-words">
                    {item.description}
                  </p>
                )}
                <div className="border-border mt-auto flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-sm">
                  <Badge variant="outline">{t(item.state)}</Badge>
                  <span className="min-w-0 text-right break-words">
                    {owners?.map((owner) => owner.name).join(", ") || item.role}
                  </span>
                </div>
              </Link>
              <DropdownMenu.Root modal={false}>
                <DropdownMenu.Trigger asChild>
                  <Button
                    variant="outline"
                    size="icon"
                    className="absolute top-4 right-4"
                    aria-label={`${catalog("moreActions")}: ${item.name}`}
                  >
                    <Icon name="more" size="sm" />
                  </Button>
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    align="end"
                    sideOffset={4}
                    className="border-border bg-popover text-popover-foreground z-50 rounded-lg border p-2"
                  >
                    <DropdownMenu.Item disabled className="text-muted-foreground px-3 py-2 text-sm">
                      {t("empty")}
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            </li>
          );
        })}
      </ul>
      {!visible.length && (
        <p className="text-muted-foreground py-6 text-sm">
          {t(items.length ? "noMatches" : "empty")}
        </p>
      )}
    </section>
  );
}
