"use client";
import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import {
  corporateCatalogSearchAction,
  corporateCatalogVersionsAction,
  corporateMutationAction,
} from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { RefineSurface } from "@/components/molecules/filter-surface";
import { Link, useRouter } from "@/lib/i18n/navigation";
import type {
  CorporateCatalogAssignment,
  CorporateCatalogAssignmentRequest,
} from "@/lib/api/generated/types.gen";
import { CatalogItemMenu } from "@/components/organisms/catalog-item-menu";
import { ObjectCard, type OwnerCardItem } from "@/components/organisms/object-card";
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
}) {
  const h = useTranslations("hub");
  const tc = useTranslations("catalog");
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<"setup" | "component">("setup");
  const [results, setResults] = useState<{ id: string; name: string }[]>([]);
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(null);
  const [versions, setVersions] = useState<string[]>([]);
  const [version, setVersion] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedKinds, setSelectedKinds] = useState<string[]>([]);
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const currentItems = items.filter((item) => item.state === "current");
  const filteredItems = currentItems.filter((item) => {
    const text = `${item.display_name ?? ""} ${item.stable_id}`.toLocaleLowerCase();
    return (
      (!query || text.includes(query.toLocaleLowerCase())) &&
      (!selectedKinds.length || selectedKinds.includes(item.object_kind))
    );
  });
  async function search(query: string) {
    setBusy(true);
    setMessage(null);
    setSelected(null);
    setVersions([]);
    setVersion("");
    try {
      const result = await corporateCatalogSearchAction({ kind, query, csrfToken });
      if (result.ok) setResults(result.items);
      else setMessage(result.message);
    } finally {
      setBusy(false);
    }
  }
  async function choose(item: { id: string; name: string }) {
    setBusy(true);
    setMessage(null);
    setSelected(item);
    setVersions([]);
    setVersion("");
    try {
      const result = await corporateCatalogVersionsAction({ kind, id: item.id, csrfToken });
      if (result.ok) {
        setVersions(result.versions);
        setVersion(result.versions[0] ?? "");
      } else setMessage(result.message);
    } finally {
      setBusy(false);
    }
  }
  async function save(removing?: CorporateCatalogAssignment) {
    if (!canManage || (!removing && (!selected || !version))) return;
    const effect = {
      subject_kind: subjectKind,
      subject_id: subjectId,
      object_kind: removing?.object_kind ?? kind,
      stable_id: removing?.stable_id ?? selected?.id ?? "",
      version: removing?.version ?? version,
      state: removing ? "retired" : "current",
      expected_revision:
        removing?.revision ??
        items.find(
          (item) =>
            !item.source_team_id &&
            item.object_kind === kind &&
            item.stable_id === selected?.id &&
            item.version === version,
        )?.revision ??
        0,
    } satisfies Omit<
      CorporateCatalogAssignmentRequest,
      "schema_version" | "authorization_revision" | "idempotency_key"
    >;
    const fingerprint = JSON.stringify(effect);
    if (retry.current?.effect !== fingerprint)
      retry.current = { effect: fingerprint, key: crypto.randomUUID() };
    setBusy(true);
    setMessage(null);
    try {
      const result = await corporateMutationAction({
        organizationId,
        csrfToken,
        path: `/v1/corporate/organizations/${organizationId}/catalog-assignments`,
        method: "PUT",
        body: {
          ...effect,
          schema_version: 1,
          authorization_revision: authorizationRevision,
          idempotency_key: retry.current.key,
        },
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      retry.current = null;
      setAdding(false);
      router.refresh();
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
      <div className="mb-4 flex justify-end">
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
                    {item.source_team_id ? (
                      <Link
                        href={`/corporate/teams/${item.source_team_id}`}
                        className="text-muted-foreground text-sm underline underline-offset-4"
                      >
                        {h("viaTeam")}
                      </Link>
                    ) : null}
                    {canManage && !item.source_team_id ? (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        onClick={() => {
                          void save(item);
                        }}
                      >
                        {h("unlink")}
                      </Button>
                    ) : null}
                    <CatalogItemMenu
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
      {canManage && (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => {
            setAdding(!adding);
          }}
        >
          {h(adding ? "cancel" : "assignCatalog")}
        </Button>
      )}
      {adding && (
        <div className="max-w-xl space-y-4">
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              const query = new FormData(event.currentTarget).get("query");
              void search(typeof query === "string" ? query : "");
            }}
          >
            <fieldset disabled={busy} className="space-y-3">
              <Label htmlFor="assignment-kind">{h("objectKind")}</Label>
              <select
                id="assignment-kind"
                className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
                value={kind}
                onChange={(event) => {
                  const value = event.target.value;
                  if (value === "setup" || value === "component") {
                    setKind(value);
                    setResults([]);
                    setSelected(null);
                    setVersion("");
                  }
                }}
              >
                <option value="setup">{h("setup")}</option>
                <option value="component">{h("component")}</option>
              </select>
              <Label htmlFor="assignment-query">{h("search")}</Label>
              <Input id="assignment-query" name="query" maxLength={200} />
              <Button type="submit">{h("search")}</Button>
            </fieldset>
          </form>
          <ul className="divide-border divide-y">
            {results.map((item) => (
              <li key={item.id} className="py-2">
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    void choose(item);
                  }}
                >
                  {item.name}
                </Button>
              </li>
            ))}
          </ul>
          {selected && (
            <div className="space-y-3">
              <p className="font-medium">{selected.name}</p>
              <Label htmlFor="assignment-version">{h("exactVersion")}</Label>
              <select
                id="assignment-version"
                className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
                value={version}
                disabled={busy}
                onChange={(event) => {
                  setVersion(event.target.value);
                }}
              >
                {versions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              <Button
                disabled={busy || !version}
                onClick={() => {
                  void save();
                }}
              >
                {h("save")}
              </Button>
            </div>
          )}
        </div>
      )}
      {message && (
        <p role="alert" className="text-sm">
          {message}
        </p>
      )}
    </DetailAccordion>
  );
}
