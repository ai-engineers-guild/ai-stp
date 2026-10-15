"use client";

import { useState } from "react";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { MenuItem, Menu, MenuTrigger, MenuContent } from "@/components/atoms/menu";
import { EntityActionItems } from "@/components/organisms/entity-action-items";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/atoms/dialog";
import { Link } from "@/lib/i18n/navigation";
import { Icon, type IconName } from "@/theme";
import { technologyAreaIcon } from "@/lib/technology-taxonomy";
import {
  useLandscapePresentation,
  versions,
  type LandscapeAreaGroup,
  type LandscapeState,
} from "./technology-landscape-state";
import { TechnologyLandscapeTable } from "./technology-landscape-table";

const CATEGORY_LIMIT = 5;
const TECHNOLOGY_LIMIT = 5;

export function TechnologyLandscapeResults(props: Parameters<typeof useLandscapePresentation>[0]) {
  const state = useLandscapePresentation(props);
  return (
    <div className="space-y-3">
      {state.grouped ? (
        <TechnologyLandscapeMap state={state} />
      ) : (
        <TechnologyLandscapeTable state={state} />
      )}
      <TechnologyLandscapeDialog state={state} />
    </div>
  );
}

export function TechnologyLandscapeMap({ state }: { state: LandscapeState }) {
  const { w, groups } = state;
  return (
    <section>
      <h2 className="text-xl font-medium">{w("landscapeHeading")}</h2>
      <p className="text-muted-foreground mb-3 text-sm">{w("landscapeDescription")}</p>
      <div className="technology-map-grid">
        {groups.map((group) => (
          <LandscapeAreaCard
            key={group.key}
            group={group}
            icon={technologyAreaIcon(group.areaId ?? group.name)}
            state={state}
          />
        ))}
      </div>
    </section>
  );
}

function LandscapeAreaCard({
  group,
  icon,
  state,
}: {
  group: LandscapeAreaGroup;
  icon: IconName;
  state: LandscapeState;
}) {
  const { w, setActive } = state;
  const [allCategories, setAllCategories] = useState(false);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [allTech, setAllTech] = useState<ReadonlySet<string>>(new Set());
  const visible = allCategories ? group.categories : group.categories.slice(0, CATEGORY_LIMIT);
  const hiddenCount = group.categories.length - visible.length;
  function toggleCategory(key: string) {
    setOpen((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }
  function expandAll() {
    setAllCategories(true);
    setOpen(new Set(group.categories.map((category) => category.key)));
  }
  function collapseAll() {
    setAllCategories(false);
    setOpen(new Set());
    setAllTech(new Set());
  }
  return (
    <section className="technology-domain">
      <header>
        <Icon name={icon} />
        <h3>{group.name}</h3>
        {group.areaId ? (
          <Menu>
            <MenuTrigger asChild>
              <Button size="icon" variant="ghost" className="size-7" aria-label={w("areaActions")}>
                <Icon name="more" size="sm" />
              </Button>
            </MenuTrigger>
            <MenuContent>
              <EntityActionItems
                subject={{ kind: "area", id: group.areaId, view: "landscape" }}
                entries={{
                  expand_all: <MenuItem onSelect={expandAll}>{w("expandAll")}</MenuItem>,
                  collapse_all: <MenuItem onSelect={collapseAll}>{w("collapseAll")}</MenuItem>,
                  open_technologies: (
                    <MenuItem asChild>
                      <Link href={`/corporate/technologies?area_ids=${group.areaId}`}>
                        {w("openTechnologies")}
                      </Link>
                    </MenuItem>
                  ),
                }}
              />
            </MenuContent>
          </Menu>
        ) : null}
      </header>
      {!group.categories.length && (
        <p className="text-muted-foreground text-xs">{w("emptyArea")}</p>
      )}
      {visible.map((category) => (
        <div key={category.key} className="space-y-1">
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground focus-visible:ring-ring flex min-h-6 w-full items-center gap-1.5 rounded-sm text-left text-xs focus-visible:ring-2 focus-visible:outline-none"
            aria-expanded={open.has(category.key)}
            onClick={() => {
              toggleCategory(category.key);
            }}
          >
            <Icon
              name={open.has(category.key) ? "chevronDown" : "chevronRight"}
              size="sm"
              className="shrink-0"
            />
            <span className="min-w-0 flex-1 truncate">{category.name}</span>
            <Badge variant="secondary" className="shrink-0">
              {category.rows.length}
            </Badge>
          </button>
          {open.has(category.key) && (
            <div className="flex flex-wrap gap-2 pl-4">
              {(allTech.has(category.key)
                ? category.rows
                : category.rows.slice(0, TECHNOLOGY_LIMIT)
              ).map((row) => (
                <Button
                  key={row.technology.technology_id}
                  variant="secondary"
                  className="technology-chip"
                  onClick={() => {
                    setActive(row);
                  }}
                >
                  {row.technology.name}
                </Button>
              ))}
              {category.rows.length > TECHNOLOGY_LIMIT && (
                <Button
                  variant="ghost"
                  className="technology-chip"
                  aria-expanded={allTech.has(category.key)}
                  aria-label={w("moreTechnologies", {
                    count: category.rows.length - TECHNOLOGY_LIMIT,
                  })}
                  onClick={() => {
                    setAllTech((previous) => {
                      const next = new Set(previous);
                      if (next.has(category.key)) next.delete(category.key);
                      else next.add(category.key);
                      return next;
                    });
                  }}
                >
                  {allTech.has(category.key)
                    ? w("showLess")
                    : `+${category.rows.length - TECHNOLOGY_LIMIT}`}
                </Button>
              )}
            </div>
          )}
        </div>
      ))}
      {hiddenCount > 0 ? (
        <Button
          variant="ghost"
          className="technology-chip self-start"
          aria-label={w("moreCategories", { count: hiddenCount })}
          onClick={() => {
            setAllCategories(true);
          }}
        >
          +{hiddenCount}
        </Button>
      ) : allCategories && group.categories.length > CATEGORY_LIMIT ? (
        <Button
          variant="ghost"
          className="technology-chip self-start"
          onClick={() => {
            setAllCategories(false);
          }}
        >
          {w("showLess")}
        </Button>
      ) : null}
    </section>
  );
}

export function TechnologyLandscapeDialog({ state }: { state: LandscapeState }) {
  const { t, w, active, setActive, classification } = state;
  return (
    <Dialog
      open={active !== null}
      onOpenChange={(open) => {
        if (!open) setActive(null);
      }}
    >
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        <DialogTitle>{active?.technology.name}</DialogTitle>
        <DialogDescription>
          {active?.technology.description || w("technologyUsage")}
        </DialogDescription>
        {active && (
          <>
            <p className="text-sm">
              {classification(active, true)} / {classification(active, false)}
            </p>
            <p className="text-sm">
              {w("versions")}: {versions(active)}
            </p>
            <ul className="divide-border divide-y">
              {active.projects.map((project) => (
                <li key={project.project_id} className="space-y-2 py-3">
                  <Link
                    className="font-medium underline underline-offset-4"
                    href={`/corporate/projects/${project.project_id}`}
                  >
                    {project.name}
                  </Link>
                  {project.usage.facts.map((fact, index) => (
                    <div key={index} className="text-sm">
                      <span>
                        {t(`values.${fact.context}`)} · {fact.version || "—"} ·{" "}
                        {t(`values.${fact.review}`)}
                      </span>
                      <ul className="text-muted-foreground text-xs">
                        {fact.evidence.map((e, i) => (
                          <li key={i}>{e.path ?? e.reference ?? e.source}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </li>
              ))}
            </ul>
            <Button asChild variant="outline">
              <Link href={`/corporate/technologies/${active.technology.technology_id}`}>
                {w("openRegistry")}
              </Link>
            </Button>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
