"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Select } from "@/components/atoms/select";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/atoms/dialog";
import { PagePager } from "@/components/molecules/page-pager";
import {
  AreaLifecycleControls,
  CategoryLifecycleControls,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { Link } from "@/lib/i18n/navigation";
import { useTechnologyTaxonomy } from "@/lib/technology-taxonomy";
import type { AreaView, CategoryView } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";

const PAGE_SIZE = 12;

type TaxonomyEntry = CategoryView | AreaView;

function entryId(kind: "area" | "category", entry: TaxonomyEntry) {
  return kind === "area"
    ? (entry as AreaView).area_id
    : (entry as CategoryView).category_id;
}

function areaOf(kind: "area" | "category", entry: TaxonomyEntry) {
  return kind === "category" ? ((entry as CategoryView).area_id ?? null) : null;
}

function entryKey(kind: "area" | "category", entry: TaxonomyEntry) {
  return `${kind}-${entryId(kind, entry)}`;
}

export function TaxonomyDirectory({
  kind,
  items,
  areas,
  authority,
  canCreate,
  canUpdate,
  canRemove,
  detailBase,
}: {
  kind: "area" | "category";
  items: readonly TaxonomyEntry[];
  areas: readonly AreaView[];
  authority: GovernanceAuthority;
  canCreate: boolean;
  canUpdate: boolean;
  canRemove: boolean;
  detailBase?: string | undefined;
}) {
  const t = useTranslations("technology");
  const w = useTranslations("technology.workspace");
  const a = useTranslations("technology.areas");
  const h = useTranslations("hub");
  const localize = useTechnologyTaxonomy();
  const [query, setQuery] = useState("");
  const [areaFilter, setAreaFilter] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<TaxonomyEntry | null>(null);
  const areaById = new Map(areas.map((area) => [area.area_id, localize(area)]));
  const needle = query.trim().toLocaleLowerCase();
  const filtered = items.filter(
    (item) =>
      (!needle || `${item.name} ${item.description}`.toLocaleLowerCase().includes(needle)) &&
      (!areaFilter || areaOf(kind, item) === areaFilter),
  );
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, totalPages);
  const shown = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const createKey = kind === "area" ? "areas.create" : "createCategory";
  return (
    <div className="min-w-0 space-y-5">
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-3">
        <div className="border-border bg-card flex min-w-0 flex-1 items-center gap-2 rounded-lg border px-3">
          <Icon name="search" size="sm" className="text-muted-foreground shrink-0" />
          <Input
            value={query}
            aria-label={h("search")}
            placeholder={h("search")}
            className="h-11 border-0 px-0"
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(1);
            }}
          />
        </div>
        {kind === "category" && areas.length > 0 && (
          <Select
            aria-label={a("field")}
            value={areaFilter}
            className="border-input bg-background text-foreground h-11 rounded-sm border px-3 text-sm"
            onChange={(event) => {
              setAreaFilter(event.target.value);
              setPage(1);
            }}
          >
            <option value="">{a("all")}</option>
            {areas.map((area) => (
              <option key={area.area_id} value={area.area_id}>
                {localize(area).name}
              </option>
            ))}
          </Select>
        )}
        {canCreate && (
          <Button
            type="button"
            size="lg"
            onClick={() => {
              setCreating(true);
            }}
          >
            <span aria-hidden="true" className="text-xl leading-none">
              +
            </span>
            {t(createKey)}
          </Button>
        )}
      </div>
      <p className="text-muted-foreground text-sm" aria-live="polite">
        {t("entryCount", { count: filtered.length })}
      </p>
      {shown.length ? (
        <ul className="grid min-w-0 gap-3">
          {shown.map((item) => (
            <TaxonomyCard
              key={entryKey(kind, item)}
              kind={kind}
              item={item}
              area={areaById.get(areaOf(kind, item) ?? "")}
              authority={authority}
              canUpdate={canUpdate}
              canRemove={canRemove}
              detailBase={detailBase}
              onEdit={setEditing}
            />
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground border-border rounded-lg border border-dashed p-8 text-center text-sm">
          {t("empty")}
        </p>
      )}
      {totalPages > 1 && (
        <PagePager
          label={w("pagination")}
          page={current}
          totalPages={totalPages}
          onPage={setPage}
          controls={{
            previous: t("previous"),
            next: t("next"),
            page: (value) => w("page", { page: value }),
          }}
        />
      )}
      <TaxonomyEditorDialog
        kind={kind}
        areas={areas}
        authority={authority}
        entry={null}
        open={creating}
        onOpenChange={setCreating}
      />
      <TaxonomyEditorDialog
        key={editing ? entryKey(kind, editing) : "edit-none"}
        kind={kind}
        areas={areas}
        authority={authority}
        entry={editing}
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
      />
    </div>
  );
}

function TaxonomyCard({
  kind,
  item,
  area,
  authority,
  canUpdate,
  canRemove,
  detailBase,
  onEdit,
}: {
  kind: "area" | "category";
  item: TaxonomyEntry;
  area: AreaView | undefined;
  authority: GovernanceAuthority;
  canUpdate: boolean;
  canRemove: boolean;
  detailBase: string | undefined;
  onEdit: (entry: TaxonomyEntry) => void;
}) {
  const t = useTranslations("technology");
  const h = useTranslations("hub");
  const id = entryId(kind, item);
  const title = detailBase ? (
    <Link
      href={`${detailBase}/${id}`}
      className="hover:text-primary focus-visible:ring-ring rounded-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
    >
      {item.name}
    </Link>
  ) : (
    item.name
  );
  return (
    <li className="min-w-0">
      <article className="border-border bg-card relative min-w-0 overflow-hidden rounded-lg border p-4">
        <div className="flex min-w-0 items-start gap-3 pr-11">
          <span className="bg-muted border-border text-foreground inline-flex size-10 shrink-0 items-center justify-center rounded-md border">
            <Icon name={kind === "area" ? "technology" : "filter"} size="sm" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h3 className="min-w-0 text-lg leading-tight font-medium tracking-tight break-words">
                {title}
              </h3>
              {item.state && item.state !== "active" && (
                <Badge variant={item.state === "draft" ? "warning" : "secondary"}>
                  {t(`values.${item.state}`)}
                </Badge>
              )}
              {area && <Badge variant="outline">{area.name}</Badge>}
            </div>
            {item.description ? (
              <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-relaxed break-words">
                {item.description}
              </p>
            ) : null}
          </div>
        </div>
        {canUpdate && (
          <div className="absolute top-4 right-4">
            <Menu>
              <MenuTrigger asChild>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={h("moreActions")}
                >
                  <Icon name="more" size="sm" />
                </Button>
              </MenuTrigger>
              <MenuContent>
                {detailBase && (
                  <MenuItem asChild>
                    <Link href={`${detailBase}/${id}`}>{t("openEntry")}</Link>
                  </MenuItem>
                )}
                <MenuItem
                  onSelect={() => {
                    onEdit(item);
                  }}
                >
                  {t(kind === "area" ? "areas.edit" : "editCategory")}
                </MenuItem>
              </MenuContent>
            </Menu>
          </div>
        )}
        {kind === "area" ? (
          <AreaLifecycleControls
            area={item as AreaView}
            canRemove={canRemove}
            canRestore={canUpdate}
            {...authority}
          />
        ) : (
          <CategoryLifecycleControls
            category={item as CategoryView}
            canRemove={canRemove}
            canRestore={canUpdate}
            {...authority}
          />
        )}
      </article>
    </li>
  );
}

function TaxonomyEditorDialog({
  kind,
  areas,
  authority,
  entry,
  open,
  onOpenChange,
}: {
  kind: "area" | "category";
  areas: readonly AreaView[];
  authority: GovernanceAuthority;
  entry: TaxonomyEntry | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("technology");
  const editing = entry !== null;
  const title = editing
    ? t(kind === "area" ? "areas.edit" : "editCategory")
    : t(kind === "area" ? "areas.create" : "createCategory");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{t("entryDialogDescription")}</DialogDescription>
        {open && (
          <TechnologyRegistryCreate
            kind={kind}
            {...authority}
            authorizationRevision={String(authority.authorizationRevision)}
            categories={null}
            areas={kind === "category" ? [...areas] : null}
            {...(entry && kind === "category"
              ? { initialCategory: entry as CategoryView }
              : {})}
            {...(entry && kind === "area" ? { initialArea: entry as AreaView } : {})}
            onCreated={() => {
              onOpenChange(false);
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
