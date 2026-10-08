"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import {
  useGovernanceMutation,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { Link } from "@/lib/i18n/navigation";
import type {
  CategoryView,
  TechnologyMappingEntry,
  TechnologyUnmappedEntry,
  TechnologyView,
} from "@/lib/api/generated/types.gen";

type MappingCoordinate = Pick<TechnologyMappingEntry, "kind" | "coordinate" | "technology_id">;

export async function reviewVersion(
  organizationId: string,
  baseVersion: string | null,
  entries: MappingCoordinate[],
): Promise<string> {
  const source = JSON.stringify({
    organization_id: organizationId,
    base_version: baseVersion,
    entries: entries.map((entry) => [entry.kind, entry.coordinate, entry.technology_id]).sort(),
  });
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(source));
  const marker = [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);
  return `review-${marker}`;
}

export function TechnologyMappingReview({
  entries,
  technologies,
  categories,
  baseVersion,
  canUpdate,
  ...authority
}: GovernanceAuthority & {
  entries: TechnologyUnmappedEntry[];
  technologies: TechnologyView[];
  categories: CategoryView[] | null;
  baseVersion: string | null;
  canUpdate: boolean;
}) {
  const t = useTranslations("technology");
  const [showResolved, setShowResolved] = useState(false);
  const names = new Map(technologies.map((item) => [item.technology_id, item]));
  const open = entries.filter((entry) => entry.state === "open");
  const proposed = open.filter((entry) => entry.candidate_technology_id !== null);
  const visible = showResolved ? entries : open;
  const bulk = useGovernanceMutation(authority);
  return (
    <section className="space-y-4" aria-busy={bulk.busy}>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-medium">{t("mappingQueue")}</h2>
        <Badge variant="outline">{t("mappingOpenCount", { count: open.length })}</Badge>
        {entries.length > open.length && (
          <Button
            variant="outline"
            size="lg"
            onClick={() => {
              setShowResolved((value) => !value);
            }}
          >
            {t(showResolved ? "mappingHideResolved" : "mappingShowResolved", {
              count: entries.length - open.length,
            })}
          </Button>
        )}
        {canUpdate && proposed.length > 0 && (
          <Button
            size="lg"
            disabled={bulk.busy}
            onClick={() => {
              const effect: MappingCoordinate[] = proposed.map((entry) => ({
                kind: entry.kind,
                coordinate: entry.coordinate,
                technology_id: entry.candidate_technology_id ?? "",
              }));
              void (async () => {
                const version = await reviewVersion(authority.organizationId, baseVersion, effect);
                bulk.save(
                  `/v1/corporate/organizations/${authority.organizationId}/technology-mappings/${encodeURIComponent(version)}`,
                  {
                    expected_revision: 0,
                    base_version: baseVersion,
                    entries: effect.map((entry) => ({ ...entry, provenance: "review" })),
                  },
                  "PUT",
                  () => {},
                );
              })();
            }}
          >
            {t(bulk.busy ? "saving" : "mappingApplyAll", { count: proposed.length })}
          </Button>
        )}
      </div>
      <p className="text-muted-foreground max-w-prose text-sm">{t("mappingQueueDescription")}</p>
      {bulk.message && (
        <p role="status" className="text-sm">
          {bulk.message}
        </p>
      )}
      {canUpdate && (
        <details className="space-y-3">
          <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
            {t("mappingCreateTechnology")}
          </summary>
          <TechnologyRegistryCreate
            kind="technology"
            organizationId={authority.organizationId}
            authorizationRevision={String(authority.authorizationRevision)}
            csrfToken={authority.csrfToken}
            categories={categories}
          />
        </details>
      )}
      {visible.length ? (
        <ul className="divide-border divide-y">
          {visible.map((entry) => (
            <UnmappedRow
              key={`${entry.kind}:${entry.coordinate}`}
              entry={entry}
              names={names}
              technologies={technologies}
              baseVersion={baseVersion}
              canUpdate={canUpdate}
              {...authority}
            />
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-sm">{t("mappingQueueEmpty")}</p>
      )}
    </section>
  );
}

function UnmappedRow({
  entry,
  names,
  technologies,
  baseVersion,
  canUpdate,
  ...authority
}: GovernanceAuthority & {
  entry: TechnologyUnmappedEntry;
  names: Map<string, TechnologyView>;
  technologies: TechnologyView[];
  baseVersion: string | null;
  canUpdate: boolean;
}) {
  const t = useTranslations("technology");
  const selectId = useId();
  const mutation = useGovernanceMutation(authority);
  const [chosen, setChosen] = useState<string | null>(null);
  const shownCandidate = chosen ?? entry.candidate_technology_id ?? "";
  const candidate = shownCandidate ? names.get(shownCandidate) : undefined;
  const resolved = entry.resolved_technology_id
    ? names.get(entry.resolved_technology_id)
    : undefined;
  const candidateDraft = candidate?.lifecycle === "draft";
  function review(candidateId: string | null) {
    setChosen(candidateId ?? "");
    mutation.save(
      `/v1/corporate/organizations/${authority.organizationId}/technology-unmapped-coordinates`,
      { kind: entry.kind, coordinate: entry.coordinate, candidate_technology_id: candidateId },
      "PATCH",
      () => {},
    );
  }
  function apply() {
    if (!shownCandidate) return;
    const effect: MappingCoordinate[] = [
      {
        kind: entry.kind,
        coordinate: entry.coordinate,
        technology_id: shownCandidate,
      },
    ];
    void (async () => {
      const version = await reviewVersion(authority.organizationId, baseVersion, effect);
      mutation.save(
        `/v1/corporate/organizations/${authority.organizationId}/technology-mappings/${encodeURIComponent(version)}`,
        {
          expected_revision: 0,
          base_version: baseVersion,
          entries: effect.map((item) => ({ ...item, provenance: "review" })),
        },
        "PUT",
        () => {},
      );
    })();
  }
  return (
    <li className="space-y-2 py-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <code className="font-mono text-sm break-all">{entry.coordinate}</code>
        <Badge variant="outline">{entry.kind}</Badge>
        <Badge variant={entry.state === "resolved" ? "secondary" : "warning"}>
          {t(`mappingState.${entry.state}`)}
        </Badge>
        <span className="text-muted-foreground text-sm">
          {t("mappingProjects", { count: entry.project_ids.length })}
        </span>
      </div>
      {(candidate ?? resolved) && (
        <p className="text-sm">
          {candidate && entry.state === "open" ? (
            <>
              {t("mappingCandidate")}{" "}
              <Link
                href={`/corporate/technologies/${candidate.technology_id}`}
                className="underline underline-offset-4"
              >
                {candidate.name}
              </Link>
              {candidateDraft && (
                <>
                  {" "}
                  <Badge variant="warning">{t("values.draft")}</Badge>
                </>
              )}
            </>
          ) : (
            resolved && (
              <>
                {t("mappingResolved")}{" "}
                <Link
                  href={`/corporate/technologies/${resolved.technology_id}`}
                  className="underline underline-offset-4"
                >
                  {resolved.name}
                </Link>
              </>
            )
          )}
        </p>
      )}
      {canUpdate && entry.state === "open" && (
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-56 space-y-1">
            <Label htmlFor={selectId}>{t("mappingCandidateLabel")}</Label>
            <select
              id={selectId}
              className="border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2"
              value={shownCandidate}
              disabled={mutation.busy}
              onChange={(event) => {
                review(event.target.value || null);
              }}
            >
              <option value="">{t("mappingNoCandidate")}</option>
              {technologies.map((technology) => (
                <option key={technology.technology_id} value={technology.technology_id}>
                  {technology.lifecycle === "active"
                    ? technology.name
                    : `${technology.name} (${t(`values.${technology.lifecycle}`)})`}
                </option>
              ))}
            </select>
          </div>
          <Button
            variant="outline"
            size="lg"
            disabled={mutation.busy || !shownCandidate}
            onClick={apply}
          >
            {t("mappingApply")}
          </Button>
        </div>
      )}
      {mutation.message && (
        <p role="status" className="text-sm">
          {mutation.message}
        </p>
      )}
    </li>
  );
}
