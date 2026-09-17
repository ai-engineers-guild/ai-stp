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
import { Link, useRouter } from "@/lib/i18n/navigation";
import type {
  CorporateCatalogAssignment,
  CorporateCatalogAssignmentRequest,
} from "@/lib/api/generated/types.gen";

// eslint-disable-next-line max-lines-per-function
export function CorporateCatalogAssignments({
  items,
  organizationId,
  subjectKind,
  subjectId,
  authorizationRevision,
  csrfToken,
  canManage,
}: {
  items: CorporateCatalogAssignment[];
  organizationId: string;
  subjectKind: "employee" | "team" | "project";
  subjectId: string;
  authorizationRevision: number;
  csrfToken: string;
  canManage: boolean;
}) {
  const h = useTranslations("hub");
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<"setup" | "component">("setup");
  const [results, setResults] = useState<{ id: string; name: string }[]>([]);
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(null);
  const [versions, setVersions] = useState<string[]>([]);
  const [version, setVersion] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const currentItems = items.filter((item) => item.state === "current");
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
      <ul className="divide-border divide-y">
        {currentItems.map((item) => (
          <li
            key={`${item.assignment_id}/${item.subject_id}/${item.source_team_id ?? "direct"}`}
            className="flex flex-wrap items-center justify-between gap-3 py-3"
          >
            <div>
              <Link
                href={`/catalog/${item.object_kind === "setup" ? "setups" : "components"}/${item.stable_id}/versions/${item.version}`}
                className="inline-flex min-h-11 items-center underline underline-offset-4"
              >
                {item.display_name ?? h(item.object_kind)} · {item.version}
              </Link>
              {item.source_team_id ? (
                <p className="text-muted-foreground text-sm">
                  <Link
                    href={`/corporate/teams/${item.source_team_id}`}
                    className="underline underline-offset-4"
                  >
                    {h("viaTeam")}
                  </Link>
                </p>
              ) : (
                <p className="text-muted-foreground text-sm">{h("directAssignment")}</p>
              )}
            </div>
            {canManage && !item.source_team_id && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  void save(item);
                }}
              >
                {h("unlink")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {!currentItems.length && (
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
