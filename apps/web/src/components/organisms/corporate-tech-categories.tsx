/* eslint-disable max-lines -- Category table, editor panel, icon picker, and linking dialog stay in one render owner. */
"use client";

import { useMemo, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { corporateMutation } from "@/lib/api/corporate-mutation";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/atoms/dialog";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { CatalogChoiceMenu } from "@/components/molecules/catalog-choice-menu";
import {
  CATEGORY_LUCIDE_PREFIX,
  CategoryIconBadge,
  categoryLucideName,
} from "@/components/molecules/category-icon-badge";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import {
  PeopleCheckbox,
  PeoplePager,
  PeopleSearch,
  PeopleSelect,
  peopleCellClass,
  peopleHeadClass,
  usePeopleFilters,
} from "@/components/organisms/corporate-people-ui";
import type { CategoryView, TechnologyView } from "@/lib/api/generated/types.gen";
import { downloadPeopleCsv } from "@/lib/member-export";
import {
  CATEGORY_ICON_NAMES,
  CategoryIcon,
  defaultCategoryIcon,
  type CategoryIconName,
} from "@/theme/category-icons";
import { Icon } from "@/theme";

type Props = {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number | string;
  capabilities: readonly string[];
  categories: readonly CategoryView[];
  /** Null without technology.list — linking and counts hide. */
  technologies: readonly TechnologyView[] | null;
};

/**
 * Persisted icon value (TechnologyCategoryMetadata.icon): "lucide:<name>" for
 * a registry glyph, or a media path/URL for an uploaded image.
 */
type CategoryDraft = { name: string; description: string; icon: string | null };

function IconPicker({
  value,
  onChange,
  label,
}: {
  value: CategoryIconName | null;
  onChange: (icon: CategoryIconName) => void;
  label: string;
}) {
  const t = useTranslations("technologyCategories");
  const [query, setQuery] = useState("");
  const names = CATEGORY_ICON_NAMES.filter((name) => name.toLowerCase().includes(query));
  return (
    <div className="space-y-2">
      <Input
        type="search"
        value={query}
        aria-label={t("searchIcons")}
        placeholder={t("searchIcons")}
        onChange={(event) => {
          setQuery(event.target.value.toLowerCase());
        }}
      />
      <div
        role="listbox"
        aria-label={label}
        className="border-border grid max-h-64 grid-cols-6 gap-1 overflow-y-auto rounded-sm border p-2 sm:grid-cols-8"
      >
        {names.map((name) => (
          <button
            key={name}
            type="button"
            role="option"
            aria-selected={name === value}
            title={name}
            aria-label={name}
            className={`focus-visible:ring-ring hover:bg-muted grid size-10 place-items-center rounded-sm focus-visible:ring-2 focus-visible:outline-none ${
              name === value ? "bg-primary/10 text-primary" : ""
            }`}
            onClick={() => {
              onChange(name);
            }}
          >
            <CategoryIcon name={name} className="size-5" />
          </button>
        ))}
      </div>
    </div>
  );
}

// eslint-disable-next-line max-lines-per-function, complexity
export function CorporateTechCategories({
  csrfToken,
  organizationId,
  authorizationRevision,
  capabilities,
  categories,
  technologies,
}: Props) {
  const t = useTranslations("technologyCategories");
  const tp = useTranslations("people");
  const router = useRouter();
  const filters = usePeopleFilters();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<CategoryDraft | null>(null);
  const [iconPicker, setIconPicker] = useState(false);
  const [managing, setManaging] = useState(false);
  const [linkSelection, setLinkSelection] = useState<string[]>([]);
  const [checked, setChecked] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const iconInput = useRef<HTMLInputElement | null>(null);

  const can = (permission: string) => capabilities.includes(permission);
  const canUpdate = can("category.update");
  const canDelete = can("category.delete");
  const canLink = can("technology.update") && technologies !== null;

  const linked = useMemo(() => {
    const map = new Map<string, TechnologyView[]>();
    for (const category of categories) map.set(category.category_id, []);
    for (const technology of technologies ?? []) {
      for (const id of technology.category_ids) map.get(id)?.push(technology);
    }
    return map;
  }, [categories, technologies]);

  const stateFilter = filters.get("state");
  const query = filters.get("query").trim().toLowerCase();
  const filtered = categories.filter(
    (category) =>
      (!stateFilter || (category.state ?? "active") === stateFilter) &&
      (!query ||
        [category.name, category.description].some((value) => value.toLowerCase().includes(query))),
  );
  const page = Math.min(
    Math.max(1, Number(filters.get("page")) || 1),
    Math.max(1, Math.ceil(filtered.length / 10)),
  );
  const rows = filtered.slice((page - 1) * 10, page * 10);
  const selected = categories.find((item) => item.category_id === selectedId) ?? null;
  const editing = creating || selected !== null;
  const selectedLinked = selected ? (linked.get(selected.category_id) ?? []) : [];
  const iconFor = (category: CategoryView) =>
    category.icon ?? `${CATEGORY_LUCIDE_PREFIX}${defaultCategoryIcon(category.category_id)}`;

  function openEditor(category: CategoryView | null) {
    setCreating(category === null);
    setSelectedId(category?.category_id ?? null);
    setDraft(
      category
        ? {
            name: category.name,
            description: category.description,
            icon: iconFor(category),
          }
        : {
            name: "",
            description: "",
            icon: `${CATEGORY_LUCIDE_PREFIX}${defaultCategoryIcon(`new-${Date.now()}`)}`,
          },
    );
  }

  async function uploadIcon(file: File) {
    setMessage(null);
    setUploading(true);
    try {
      const response = await fetch("/api/corporate/category-icon", {
        method: "POST",
        headers: {
          "content-type": file.type,
          "x-csrf-token": csrfToken,
          "x-locale": document.documentElement.lang,
        },
        body: file,
      });
      const result = (await response.json()) as { ok?: boolean; icon?: string; message?: string };
      if (!response.ok || !result.ok || !result.icon) {
        setMessage(result.message ?? t("iconUploadFailed"));
        return;
      }
      setDraft((current) => (current ? { ...current, icon: result.icon ?? null } : current));
    } catch {
      setMessage(t("iconUploadFailed"));
    } finally {
      setUploading(false);
      if (iconInput.current) iconInput.current.value = "";
    }
  }

  function mutate(
    path: string,
    method: "POST" | "PUT" | "PATCH" | "DELETE",
    body: unknown,
    done?: (data: unknown) => void,
  ) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutation({
        csrfToken,
        organizationId,
        path,
        method,
        body,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      setMessage(t("saved"));
      done?.(result.data);
      router.refresh();
    });
  }

  function lifecycle(category: CategoryView, target: "archived" | "active") {
    mutate(
      `/v1/corporate/organizations/${organizationId}/technology-categories/${category.category_id}/lifecycle`,
      "POST",
      {
        schema_version: 1,
        target,
        expected_revision: category.revision,
        authorization_revision: authorizationRevision,
        idempotency_key: crypto.randomUUID(),
      },
      () => {
        if (target === "archived") setSelectedId(null);
      },
    );
  }

  function save() {
    if (!draft) return;
    const path = `/v1/corporate/organizations/${organizationId}/technology-categories${creating ? "" : `/${selected?.category_id}`}`;
    mutate(
      path,
      creating ? "POST" : "PUT",
      {
        schema_version: 1,
        metadata: {
          name: draft.name,
          description: draft.description,
          icon: draft.icon,
        },
        expected_revision: creating ? 0 : (selected?.revision ?? 0),
        ...(creating ? { state: "active" } : {}),
        authorization_revision: authorizationRevision,
        idempotency_key: crypto.randomUUID(),
      },
      () => {
        setCreating(false);
      },
    );
  }

  function saveLinks() {
    if (!selected || !technologies) return;
    const categoryId = selected.category_id;
    const wanted = new Set(linkSelection);
    const changed = technologies.filter(
      (technology) =>
        technology.category_ids.includes(categoryId) !== wanted.has(technology.technology_id),
    );
    setMessage(null);
    startTransition(async () => {
      let failed = 0;
      for (const technology of changed) {
        const next = wanted.has(technology.technology_id)
          ? [...technology.category_ids, categoryId]
          : technology.category_ids.filter((id) => id !== categoryId);
        // The contract requires at least one category per technology.
        if (!next.length) {
          failed += 1;
          continue;
        }
        const result = await corporateMutation({
          csrfToken,
          organizationId,
          path: `/v1/corporate/organizations/${organizationId}/technologies/${technology.technology_id}`,
          method: "PUT",
          body: {
            schema_version: 1,
            metadata: {
              name: technology.name,
              category_ids: next,
              aliases: technology.aliases,
              description: technology.description,
              icon_url: technology.icon_url,
              official_urls: technology.official_urls,
            },
            expected_revision: technology.revision,
            authorization_revision: authorizationRevision,
            idempotency_key: crypto.randomUUID(),
          },
        });
        if (!result.ok) failed += 1;
      }
      setMessage(failed ? t("linkPartial", { count: failed }) : t("saved"));
      if (!failed) setManaging(false);
      router.refresh();
    });
  }

  const panelOpen = editing && draft !== null;

  return (
    <div
      className={
        panelOpen ? "grid min-w-0 gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]" : "min-w-0 space-y-6"
      }
    >
      <section className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <PeopleSearch
            label={t("searchCategories")}
            value={filters.get("query")}
            onChange={(value) => {
              filters.update("query", value);
            }}
          />
          <PeopleSelect
            label={t("allCategories")}
            value={stateFilter}
            onChange={(value) => {
              filters.update("state", value);
            }}
            options={[
              { value: "active", label: t("state_active") },
              { value: "draft", label: t("state_draft") },
              { value: "archived", label: t("state_archived") },
            ]}
          />
          <div className="ml-auto flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={!filtered.length}
              onClick={() => {
                downloadPeopleCsv("categories.csv", [
                  ["name", "description", "state", "revision", "technologies"],
                  ...filtered.map((category) => [
                    category.name,
                    category.description,
                    category.state ?? "active",
                    String(category.revision),
                    String(linked.get(category.category_id)?.length ?? 0),
                  ]),
                ]);
              }}
            >
              <Icon name="download" size="sm" />
              {t("export")}
            </Button>
            {can("category.create") ? (
              <Button
                type="button"
                className="h-11"
                onClick={() => {
                  openEditor(null);
                }}
              >
                <Icon name="plus" size="sm" />
                {t("addCategory")}
              </Button>
            ) : null}
          </div>
        </div>
        {checked.length ? (
          <div
            aria-live="polite"
            className="bg-muted flex items-center justify-between rounded-sm px-3 py-2 text-sm"
          >
            <span>{tp("selected", { count: checked.length })}</span>
            <div className="flex items-center gap-2">
              {canDelete ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    setMessage(null);
                    startTransition(async () => {
                      let failed = 0;
                      for (const id of checked) {
                        const category = categories.find(
                          (item) => item.category_id === id && item.state !== "archived",
                        );
                        if (!category) continue;
                        const result = await corporateMutation({
                          csrfToken,
                          organizationId,
                          path: `/v1/corporate/organizations/${organizationId}/technology-categories/${id}/lifecycle`,
                          method: "POST",
                          body: {
                            schema_version: 1,
                            target: "archived",
                            expected_revision: category.revision,
                            authorization_revision: authorizationRevision,
                            idempotency_key: crypto.randomUUID(),
                          },
                        });
                        if (!result.ok) failed += 1;
                      }
                      setMessage(failed ? t("linkPartial", { count: failed }) : t("saved"));
                      setChecked([]);
                      router.refresh();
                    });
                  }}
                >
                  {t("archiveSelected")}
                </Button>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setChecked([]);
                }}
              >
                {tp("clearSelection")}
              </Button>
            </div>
          </div>
        ) : null}
        <div
          role="region"
          aria-label={t("title")}
          // Keyboard access is required for scrolling the table on narrow viewports.
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
          tabIndex={0}
          className="border-border focus-visible:ring-ring overflow-x-auto rounded-lg border focus-visible:ring-2 focus-visible:outline-none"
        >
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr className="border-border border-b">
                <th className="w-11">
                  <PeopleCheckbox
                    label={tp("selectPage")}
                    checked={
                      Boolean(rows.length) &&
                      rows.every((category) => checked.includes(category.category_id))
                    }
                    mixed={
                      rows.some((category) => checked.includes(category.category_id)) &&
                      !rows.every((category) => checked.includes(category.category_id))
                    }
                    onChange={(value) => {
                      setChecked((current) =>
                        value
                          ? [
                              ...new Set([
                                ...current,
                                ...rows.map((category) => category.category_id),
                              ]),
                            ]
                          : current.filter((id) => !rows.some((item) => item.category_id === id)),
                      );
                    }}
                  />
                </th>
                <th scope="col" className={peopleHeadClass}>
                  {t("nameColumn")}
                </th>
                <th scope="col" className={peopleHeadClass}>
                  {t("technologiesColumn")}
                </th>
                <th scope="col" className={peopleHeadClass}>
                  {t("description")}
                </th>
                <th scope="col" className={peopleHeadClass}>
                  {t("state")}
                </th>
                <th scope="col" className={`${peopleHeadClass} w-11`}>
                  <span className="sr-only">{t("actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((category) => (
                <tr
                  key={category.category_id}
                  data-selected={selected?.category_id === category.category_id || undefined}
                  className="border-border hover:bg-muted/30 data-[selected]:bg-primary/5 cursor-pointer border-b transition-colors last:border-0"
                  onClick={() => {
                    openEditor(category);
                  }}
                >
                  <td
                    onClick={(event) => {
                      event.stopPropagation();
                    }}
                  >
                    <PeopleCheckbox
                      label={category.name}
                      checked={checked.includes(category.category_id)}
                      onChange={(value) => {
                        setChecked((current) =>
                          value
                            ? [...current, category.category_id]
                            : current.filter((id) => id !== category.category_id),
                        );
                      }}
                    />
                  </td>
                  <td className={`${peopleCellClass} font-medium`}>
                    <span className="inline-flex items-center gap-3">
                      <CategoryIconBadge
                        icon={iconFor(category)}
                        seed={category.category_id}
                        size={8}
                      />
                      <span className="whitespace-nowrap">{category.name}</span>
                    </span>
                  </td>
                  <td className={`${peopleCellClass} tabular-nums`}>
                    {technologies === null ? "—" : (linked.get(category.category_id)?.length ?? 0)}
                  </td>
                  <td className={`${peopleCellClass} text-muted-foreground max-w-72`}>
                    <span className="line-clamp-2">{category.description}</span>
                  </td>
                  <td className={peopleCellClass}>
                    <Badge
                      variant={
                        category.state === "archived"
                          ? "secondary"
                          : category.state === "draft"
                            ? "warning"
                            : "outline"
                      }
                    >
                      {t(`state_${category.state ?? "active"}`)}
                    </Badge>
                  </td>
                  <td
                    className="text-right"
                    onClick={(event) => {
                      event.stopPropagation();
                    }}
                  >
                    <CatalogChoiceMenu
                      icon="moreVertical"
                      variant="ghost"
                      align="end"
                      label={t("categoryActions", { name: category.name })}
                      options={[
                        {
                          label: t("edit"),
                          icon: "edit",
                          onSelect: () => {
                            openEditor(category);
                          },
                          disabled: !canUpdate,
                        },
                        {
                          label: t("manageTechnologies"),
                          icon: "link",
                          onSelect: () => {
                            setSelectedId(category.category_id);
                            setLinkSelection(
                              (linked.get(category.category_id) ?? []).map(
                                (technology) => technology.technology_id,
                              ),
                            );
                            setManaging(true);
                          },
                          disabled: !canLink,
                        },
                        category.state === "archived"
                          ? {
                              label: t("restore"),
                              icon: "check",
                              separatorBefore: true,
                              onSelect: () => {
                                lifecycle(category, "active");
                              },
                              disabled: !canUpdate,
                            }
                          : {
                              label: t("deleteCategory"),
                              icon: "close",
                              separatorBefore: true,
                              onSelect: () => {
                                lifecycle(category, "archived");
                              },
                              disabled: !canDelete,
                            },
                      ]}
                    />
                  </td>
                </tr>
              ))}
              {!rows.length ? (
                <tr>
                  <td colSpan={6} className="text-muted-foreground py-14 text-center text-sm">
                    {t(categories.length ? "noMatches" : "empty")}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
          <PeoplePager
            total={filtered.length}
            page={page}
            kind="members"
            onPage={(value) => {
              filters.update("page", String(value));
            }}
          />
        </div>
      </section>

      {panelOpen ? (
        <aside className="border-border bg-card h-fit min-w-0 space-y-5 rounded-lg border p-5">
          <div className="flex items-start justify-between gap-3">
            <h2 className="min-w-0 text-xl leading-tight font-medium break-words">
              {creating ? t("addCategory") : (selected?.name ?? "")}
            </h2>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={t("close")}
              onClick={() => {
                setSelectedId(null);
                setCreating(false);
                setDraft(null);
              }}
            >
              <Icon name="close" size="sm" />
            </Button>
          </div>
          <div className="space-y-2">
            <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              {t("categoryIcon")}
            </h3>
            <div className="flex items-center gap-3">
              <CategoryIconBadge
                icon={draft.icon ?? ""}
                seed={selected?.category_id ?? "new"}
                size={16}
              />
              <div className="flex flex-col gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setIconPicker(true);
                  }}
                >
                  <Icon name="edit" size="sm" />
                  {t("changeIcon")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={uploading}
                  onClick={() => {
                    iconInput.current?.click();
                  }}
                >
                  <Icon name="upload" size="sm" />
                  {uploading ? t("uploading") : t("uploadIcon")}
                </Button>
                <input
                  ref={iconInput}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  aria-label={t("uploadIcon")}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void uploadIcon(file);
                  }}
                />
              </div>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="category-name">{t("nameRequired")}</Label>
            <Input
              id="category-name"
              required
              value={draft.name}
              onChange={(event) => {
                setDraft({ ...draft, name: event.target.value });
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="category-description">{t("description")}</Label>
            <Textarea
              id="category-description"
              maxLength={2000}
              value={draft.description}
              onChange={(event) => {
                setDraft({ ...draft, description: event.target.value });
              }}
            />
            <p className="text-muted-foreground text-right text-xs tabular-nums">
              {draft.description.length}/2000
            </p>
          </div>
          {!creating && selected ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-medium">{t("linkedTechnologies")}</h3>
                {canLink ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setLinkSelection(
                        selectedLinked.map((technology) => technology.technology_id),
                      );
                      setManaging(true);
                    }}
                  >
                    <Icon name="link" size="sm" />
                    {t("manageTechnologies")}
                  </Button>
                ) : null}
              </div>
              <p className="text-muted-foreground text-sm">
                {t("linkedCount", { count: selectedLinked.length })}
              </p>
              <ul className="space-y-1 text-sm">
                {selectedLinked.slice(0, 6).map((technology) => (
                  <li key={technology.technology_id} className="truncate">
                    {technology.name}
                  </li>
                ))}
              </ul>
              {selectedLinked.length > 6 ? (
                <p className="text-muted-foreground text-sm">
                  {t("moreTechnologies", { count: selectedLinked.length - 6 })}
                </p>
              ) : null}
              <dl className="text-muted-foreground space-y-1 text-xs">
                <div className="flex justify-between gap-2">
                  <dt>{t("revision")}</dt>
                  <dd className="tabular-nums">{selected.revision}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>{t("provenance")}</dt>
                  <dd>{selected.provenance}</dd>
                </div>
              </dl>
            </div>
          ) : null}
          <div className="border-border flex flex-wrap items-center justify-between gap-2 border-t pt-4">
            {!creating && selected && canDelete && selected.state !== "archived" ? (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                disabled={busy}
                onClick={() => {
                  lifecycle(selected, "archived");
                }}
              >
                {t("deleteCategory")}
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setSelectedId(null);
                  setCreating(false);
                  setDraft(null);
                }}
              >
                {t("cancel")}
              </Button>
              <Button
                type="button"
                disabled={
                  busy || !draft.name.trim() || (creating ? !can("category.create") : !canUpdate)
                }
                onClick={save}
              >
                {busy ? t("saving") : t("saveChanges")}
              </Button>
            </div>
          </div>
        </aside>
      ) : null}

      <Dialog open={iconPicker} onOpenChange={setIconPicker}>
        <DialogContent closeLabel={t("close")} className="max-w-2xl">
          <DialogTitle>{t("chooseIcon")}</DialogTitle>
          <DialogDescription>{t("chooseIconHint")}</DialogDescription>
          {draft ? (
            <IconPicker
              value={categoryLucideName(draft.icon)}
              label={t("chooseIcon")}
              onChange={(icon) => {
                setDraft({ ...draft, icon: `${CATEGORY_LUCIDE_PREFIX}${icon}` });
                setIconPicker(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog
        open={managing}
        onOpenChange={(open) => {
          if (!open) setManaging(false);
        }}
      >
        <DialogContent closeLabel={t("close")} className="max-w-xl">
          <DialogTitle>{t("manageTechnologies")}</DialogTitle>
          <DialogDescription>{selected?.name ?? ""}</DialogDescription>
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              saveLinks();
            }}
          >
            <SearchableMultiSelect
              name="technologies"
              label={t("linkedTechnologies")}
              searchLabel={t("searchTechnologies")}
              options={(technologies ?? []).map((technology) => ({
                value: technology.technology_id,
                label: technology.name,
              }))}
              selected={linkSelection}
              onChange={setLinkSelection}
              modal
              inline
              closeLabel={t("close")}
              selectionSuffix={t("selectedSuffix")}
              emptyHint={t("searchTechnologies")}
            />
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? t("saving") : t("save")}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {message ? (
        <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
    </div>
  );
}
