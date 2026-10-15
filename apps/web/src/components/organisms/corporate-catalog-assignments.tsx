/* eslint-disable max-lines -- The assignment section and its dialog share selection and retry state. */
"use client";
import { Select } from "@/components/atoms/select";
import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { corporateCatalogSearchAction, corporateCatalogVersionsAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/atoms/dialog";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { PeopleCheckbox } from "@/components/molecules/people-ui";
import { RefineSurface } from "@/components/molecules/filter-surface";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import { useRouter } from "@/lib/i18n/navigation";
import type {
  CorporateCatalogAssignment,
  CorporateCatalogAssignmentRequest,
} from "@/lib/api/generated/types.gen";
import { CatalogItemMenu } from "@/components/organisms/catalog-item-menu";
import {
  ObjectCard,
  type CatalogAuthor,
  type OwnerCardItem,
} from "@/components/organisms/object-card";
import { assignmentCardItem } from "@/lib/assignment-card";
import { Icon } from "@/theme";

// eslint-disable-next-line max-lines-per-function
export function CorporateCatalogAssignments({
  items,
  cards,
  organizationId,
  subjectKind,
  subjectId,
  authorizationRevision,
  csrfToken,
  canManage,
  authors,
}: {
  items: CorporateCatalogAssignment[];
  /** Resolved catalog cards keyed by assignment_id; falls back to identity-only rows. */
  cards?: Record<string, OwnerCardItem>;
  organizationId: string;
  subjectKind: "employee" | "team" | "project" | "technology";
  subjectId: string;
  authorizationRevision: number;
  csrfToken: string;
  canManage: boolean;
  authors?: Record<string, CatalogAuthor>;
}) {
  const h = useTranslations("hub");
  const tc = useTranslations("catalog");
  const common = useTranslations("common");
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<"all" | "setup" | "component">("all");
  const [results, setResults] = useState<
    { kind: "setup" | "component"; id: string; name: string }[]
  >([]);
  const [selected, setSelected] = useState<
    { kind: "setup" | "component"; id: string; name: string; version: string; versions: string[] }[]
  >([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [pendingChoices, setPendingChoices] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedKinds, setSelectedKinds] = useState<string[]>([]);
  const retry = useRef(new Map<string, string>());
  const searchRequest = useRef(0);
  const pendingSelection = useRef(new Set<string>());
  const currentItems = items.filter((item) => item.state === "current");
  const filteredItems = currentItems.filter((item) => {
    const text = `${item.display_name ?? ""} ${item.stable_id}`.toLocaleLowerCase();
    return (
      (!query || text.includes(query.toLocaleLowerCase())) &&
      (!selectedKinds.length || selectedKinds.includes(item.object_kind))
    );
  });
  async function search(query: string, filter = kind) {
    const request = ++searchRequest.current;
    setBusy(true);
    setMessage(null);
    try {
      const kinds = filter === "all" ? (["setup", "component"] as const) : [filter];
      const pages = await Promise.all(
        kinds.map(async (entryKind) => ({
          kind: entryKind,
          result: await corporateCatalogSearchAction({ kind: entryKind, query, csrfToken }),
        })),
      );
      const failed = pages.find((page) => !page.result.ok);
      if (request !== searchRequest.current) return;
      if (failed && !failed.result.ok) setMessage(failed.result.message);
      setResults(
        pages.flatMap(({ kind: entryKind, result }) =>
          result.ok ? result.items.map((item) => ({ ...item, kind: entryKind })) : [],
        ),
      );
    } catch {
      if (request === searchRequest.current) setMessage(common("requestFailed"));
    } finally {
      if (request === searchRequest.current) setBusy(false);
    }
  }
  async function choose(item: { kind: "setup" | "component"; id: string; name: string }) {
    const identity = `${item.kind}:${item.id}`;
    if (pendingSelection.current.has(identity)) return;
    if (selected.some((entry) => entry.kind === item.kind && entry.id === item.id)) {
      setSelected((entries) =>
        entries.filter((entry) => entry.kind !== item.kind || entry.id !== item.id),
      );
      return;
    }
    pendingSelection.current.add(identity);
    setPendingChoices((count) => count + 1);
    setMessage(null);
    try {
      const result = await corporateCatalogVersionsAction({
        kind: item.kind,
        id: item.id,
        csrfToken,
      });
      const availableVersions = result.ok ? result.versions : [];
      const firstVersion = availableVersions[0];
      if (firstVersion) {
        setSelected((entries) => [
          ...entries,
          { ...item, version: firstVersion, versions: availableVersions },
        ]);
      } else setMessage(result.ok ? h("noMatches") : result.message);
    } catch {
      setMessage(common("requestFailed"));
    } finally {
      pendingSelection.current.delete(identity);
      setPendingChoices((count) => count - 1);
    }
  }
  async function writeAssignment(
    effect: Omit<
      CorporateCatalogAssignmentRequest,
      "schema_version" | "authorization_revision" | "idempotency_key"
    >,
  ) {
    const fingerprint = JSON.stringify(effect);
    const idempotencyKey = retry.current.get(fingerprint) ?? crypto.randomUUID();
    retry.current.set(fingerprint, idempotencyKey);
    const result = await corporateMutation({
      organizationId,
      csrfToken,
      path: `/v1/corporate/organizations/${organizationId}/catalog-assignments`,
      method: "PUT",
      body: {
        ...effect,
        schema_version: 1,
        authorization_revision: authorizationRevision,
        idempotency_key: idempotencyKey,
      },
    });
    if (result.ok) retry.current.delete(fingerprint);
    return result;
  }
  async function unlink(removing: CorporateCatalogAssignment) {
    if (!canManage) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await writeAssignment({
        subject_kind: subjectKind,
        subject_id: subjectId,
        object_kind: removing.object_kind,
        stable_id: removing.stable_id,
        selector: removing.selector,
        version: removing.version,
        harness: removing.harness,
        passport_digest: removing.passport_digest,
        state: "retired",
        expected_revision: removing.revision,
      });
      if (!result.ok) setMessage(result.message);
      else router.refresh();
    } catch {
      setMessage(common("requestFailed"));
    } finally {
      setBusy(false);
    }
  }
  async function assignSelected() {
    if (!canManage || !selected.length) return;
    setBusy(true);
    setMessage(null);
    const failed: typeof selected = [];
    let firstError: string | null = null;
    try {
      for (const item of selected) {
        try {
          const result = await writeAssignment({
            subject_kind: subjectKind,
            subject_id: subjectId,
            object_kind: item.kind,
            stable_id: item.id,
            selector: "exact",
            version: item.version,
            harness: null,
            passport_digest: null,
            state: "current",
            expected_revision:
              items.find(
                (existing) =>
                  !existing.source_team_id &&
                  existing.object_kind === item.kind &&
                  existing.stable_id === item.id &&
                  existing.version === item.version,
              )?.revision ?? 0,
          });
          if (!result.ok) {
            failed.push(item);
            firstError ??= result.message;
          }
        } catch {
          failed.push(item);
          firstError ??= common("requestFailed");
        }
      }
      setSelected(failed);
      if (failed.length) setMessage(firstError ?? common("requestFailed"));
      else setAdding(false);
      if (failed.length !== selected.length) router.refresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <DetailAccordion
      title={h("catalogAssignments")}
      summary={`${currentItems.length}`}
      defaultOpen={canManage}
    >
      <div className="mb-4 flex items-center justify-end gap-3">
        {canManage ? (
          <Button
            className="mr-auto"
            disabled={busy}
            onClick={() => {
              setAdding(true);
              void search("");
            }}
          >
            {h("assignCatalog")}
          </Button>
        ) : null}
        <Button
          type="button"
          variant={filtersOpen || query || selectedKinds.length ? "default" : "outline"}
          onClick={() => {
            setFiltersOpen((open) => !open);
          }}
        >
          <Icon name="controls" size="sm" />
          {h("filters")}
        </Button>
      </div>
      {filtersOpen ? (
        <RefineSurface
          id={`assignment-filters-${subjectKind}`}
          labels={{
            filtersButton: h("filters"),
            refineButton: h("filterTitle"),
            closeFilters: h("closeFilters"),
          }}
          onClose={() => {
            setFiltersOpen(false);
          }}
        >
          <div className="grid gap-5 md:grid-cols-2">
            <label className="space-y-2 text-sm">
              <span className="font-medium">{h("search")}</span>
              <Input
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                }}
              />
            </label>
            <label className="space-y-2 text-sm">
              <span className="font-medium">{h("objectKind")}</span>
              <SearchableMultiSelect
                name="assignment-object-kind"
                label={h("objectKind")}
                searchLabel={h("search")}
                options={[
                  { value: "setup", label: h("setup") },
                  { value: "component", label: h("component") },
                ]}
                selected={selectedKinds}
                onChange={setSelectedKinds}
                closeLabel={h("closeFilters")}
                modal
              />
            </label>
          </div>
        </RefineSurface>
      ) : null}
      <ul className="border-border divide-border grid min-w-0 divide-y overflow-hidden rounded-lg border">
        {filteredItems.map((item) => {
          const card = cards?.[item.assignment_id] ?? assignmentCardItem(item);
          const version =
            card.catalog_item &&
            "latest_version" in card.catalog_item &&
            typeof card.catalog_item.latest_version === "string"
              ? card.catalog_item.latest_version
              : item.version;
          return (
            <li
              key={`${item.assignment_id}/${item.subject_id}/${item.source_team_id ?? "direct"}`}
              className="min-w-0"
            >
              <ObjectCard
                {...(card.catalog_item?.publisher_id && authors?.[card.catalog_item.publisher_id]
                  ? { author: authors[card.catalog_item.publisher_id] }
                  : {})}
                kind={item.object_kind}
                item={card}
                href={`/catalog/${item.object_kind === "setup" ? "setups" : "components"}/${item.stable_id}`}
                labels={{
                  version: tc("version"),
                  harness: tc("harness"),
                  tags: tc("tags"),
                  type: tc("type"),
                  publisher: tc("publisher"),
                  likes: tc("likes"),
                  componentKind: tc("componentKind"),
                  setupKind: tc("setupKind"),
                  moreActions: tc("moreActions"),
                  copyCli: tc("copyCli"),
                  copyId: tc("copyId"),
                  copyUrl: tc("copyUrl"),
                  copied: tc("copied"),
                  report: tc("report"),
                  reportSetup: tc("reportSetup"),
                  like: tc("likeMenu"),
                  unlike: tc("unlikeMenu"),
                  publicVisibility: tc("public"),
                  privateVisibility: tc("private"),
                }}
                view="list"
                ownerActions={
                  <div className="flex min-w-0 flex-wrap items-center justify-end gap-3">
                    <CatalogItemMenu
                      {...(!item.source_team_id
                        ? {
                            assignmentId: item.assignment_id,
                            onUnlink: () => {
                              void unlink(item);
                            },
                          }
                        : {})}
                      kind={item.object_kind}
                      stableId={item.stable_id}
                      version={version}
                      href={`/catalog/${item.object_kind === "setup" ? "setups" : "components"}/${item.stable_id}`}
                      objectName={card.name}
                      labels={{
                        more: tc("moreActions"),
                        copyUrl: tc("copyUrl"),
                        copyCli: tc("copyCli"),
                        copyId: tc("copyId"),
                        copied: tc("copied"),
                        report: item.object_kind === "setup" ? tc("reportSetup") : tc("report"),
                        like: tc("likeMenu"),
                        unlike: tc("unlikeMenu"),
                      }}
                    />
                  </div>
                }
              />
            </li>
          );
        })}
      </ul>
      {!filteredItems.length && (
        <p className="text-muted-foreground text-sm">{h("noAssignments")}</p>
      )}
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent className="max-h-[min(46rem,calc(100vh-2rem))] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{h("assignCatalog")}</DialogTitle>
            <DialogDescription>{h("search")}</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-3 sm:grid-cols-[1fr_auto_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              void search(searchQuery);
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="assignment-query">{h("search")}</Label>
              <Input
                id="assignment-query"
                value={searchQuery}
                maxLength={200}
                onChange={(event) => {
                  setSearchQuery(event.target.value);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="assignment-kind">{h("objectKind")}</Label>
              <Select
                id="assignment-kind"
                className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
                value={kind}
                onChange={(event) => {
                  const value = event.target.value as "all" | "setup" | "component";
                  setKind(value);
                  void search(searchQuery, value);
                }}
              >
                <option value="all">{h("all")}</option>
                <option value="setup">{h("setup")}</option>
                <option value="component">{h("component")}</option>
              </Select>
            </div>
            <Button type="submit" className="self-end" disabled={busy}>
              {h("search")}
            </Button>
          </form>
          <ul className="grid max-h-64 min-w-0 gap-2 overflow-y-auto sm:grid-cols-2">
            {results.map((item) => {
              const checked = selected.some(
                (entry) => entry.kind === item.kind && entry.id === item.id,
              );
              return (
                <li
                  key={`${item.kind}:${item.id}`}
                  className="border-border min-w-0 rounded-lg border p-3"
                >
                  <div className="flex min-h-11 min-w-0 items-center gap-3 text-sm">
                    <PeopleCheckbox
                      label={item.name}
                      checked={checked}
                      onChange={() => {
                        if (!busy) void choose(item);
                      }}
                    />
                    <span className="min-w-0 font-medium break-words">{item.name}</span>
                    <span className="text-muted-foreground ml-auto text-xs">{h(item.kind)}</span>
                  </div>
                </li>
              );
            })}
          </ul>
          {selected.length ? (
            <div className="border-border space-y-2 border-t pt-4">
              {selected.map((item) => (
                <div
                  key={`${item.kind}:${item.id}`}
                  className="grid items-center gap-2 sm:grid-cols-[1fr_auto]"
                >
                  <span className="min-w-0 truncate text-sm">{item.name}</span>
                  <Select
                    aria-label={`${item.name} ${h("exactVersion")}`}
                    className="border-input bg-background min-h-11 rounded-sm border px-3 text-sm"
                    value={item.version}
                    onChange={(event) => {
                      setSelected((entries) =>
                        entries.map((entry) =>
                          entry.kind === item.kind && entry.id === item.id
                            ? { ...entry, version: event.target.value }
                            : entry,
                        ),
                      );
                    }}
                  >
                    {item.versions.map((version) => (
                      <option key={version} value={version}>
                        {version}
                      </option>
                    ))}
                  </Select>
                </div>
              ))}
            </div>
          ) : null}
          {message ? (
            <p role="alert" className="text-destructive text-sm">
              {message}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setAdding(false);
              }}
            >
              {h("cancel")}
            </Button>
            <Button
              type="button"
              disabled={busy || pendingChoices > 0 || !selected.length}
              onClick={() => {
                void assignSelected();
              }}
            >
              {h("assign")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {message && !adding && (
        <p role="alert" className="text-sm">
          {message}
        </p>
      )}
    </DetailAccordion>
  );
}
