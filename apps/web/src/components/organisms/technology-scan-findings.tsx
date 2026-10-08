"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import { Sheet, SheetContent, SheetTitle } from "@/components/atoms/sheet";
import {
  useGovernanceMutation,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import { reviewVersion } from "@/components/organisms/technology-mapping-review";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { Link } from "@/lib/i18n/navigation";
import type {
  AreaView,
  CategoryView,
  TechnologyScanFinding,
  TechnologyView,
} from "@/lib/api/generated/types.gen";

export function TechnologyScanFindings({
  findings,
  technologies,
  categories,
  areas,
  baseVersion,
  canUpdate,
  ...authority
}: GovernanceAuthority & {
  findings: TechnologyScanFinding[];
  technologies: TechnologyView[];
  categories: CategoryView[] | null;
  areas: AreaView[] | null;
  baseVersion: string | null;
  canUpdate: boolean;
}) {
  const [active, setActive] = useState<TechnologyScanFinding | null>(null);
  const names = new Map(technologies.map((item) => [item.technology_id, item]));
  const categoryNames = new Map(categories?.map((item) => [item.category_id, item]) ?? []);
  const areaNames = new Map(areas?.map((item) => [item.area_id, item.name]) ?? []);

  return (
    <>
      <FindingsTable
        findings={findings}
        names={names}
        categoryNames={categoryNames}
        areaNames={areaNames}
        onSelect={setActive}
      />
      <Sheet
        open={active !== null}
        onOpenChange={(open) => {
          if (!open) setActive(null);
        }}
      >
        <SheetContent className="w-[min(calc(100vw-1rem),28rem)] gap-4 overflow-y-auto p-6">
          <SheetTitle className="font-mono text-sm break-all">{active?.coordinate}</SheetTitle>
          {active && (
            <FindingReview
              key={`${active.kind}:${active.coordinate}`}
              finding={active}
              technologies={technologies}
              categories={categories}
              areas={areas}
              baseVersion={baseVersion}
              canUpdate={canUpdate}
              {...authority}
            />
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}

function FindingsTable({
  findings,
  names,
  categoryNames,
  areaNames,
  onSelect,
}: {
  findings: TechnologyScanFinding[];
  names: Map<string, TechnologyView>;
  categoryNames: Map<string, CategoryView>;
  areaNames: Map<string, string>;
  onSelect: (finding: TechnologyScanFinding) => void;
}) {
  const t = useTranslations("technology");
  const scans = useTranslations("technology.scans");
  const columns = useTranslations("technology.scans.columns");
  const kinds = useTranslations("technology.scans.versionKind");
  const versionKindLabel = {
    unknown: kinds("unknown"),
    declared_range: kinds("declared_range"),
    observed_version: kinds("observed_version"),
  };

  function classification(technologyId: string | null) {
    const technology = technologyId ? names.get(technologyId) : undefined;
    if (!technology) return null;
    const parts = technology.category_ids
      .map((id) => {
        const category = categoryNames.get(id);
        if (!category) return null;
        const area = category.area_id ? areaNames.get(category.area_id) : null;
        return area ? `${area} / ${category.name}` : category.name;
      })
      .filter((part): part is string => part !== null);
    return parts.length ? parts.join(", ") : null;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">{scans("findings")}</caption>
        <thead className="border-border border-b">
          <tr>
            <th scope="col" className="p-3 font-medium">
              {columns("found")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {t("technology")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("classification")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {t("version")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("evidence")}
            </th>
            <th scope="col" className="p-3 font-medium">
              {columns("status")}
            </th>
          </tr>
        </thead>
        <tbody>
          {findings.map((finding) => {
            const technologyId = finding.technology_id ?? finding.candidate_technology_id;
            const technology = technologyId ? names.get(technologyId) : undefined;
            return (
              <tr
                key={`${finding.kind}:${finding.coordinate}`}
                className="border-border border-b align-top"
              >
                <th scope="row" className="p-3 font-medium">
                  <button
                    type="button"
                    className="min-h-11 cursor-pointer text-left underline underline-offset-4"
                    onClick={() => {
                      onSelect(finding);
                    }}
                  >
                    <code className="font-mono text-sm break-all">{finding.coordinate}</code>
                  </button>
                  <Badge variant="outline" className="ml-2">
                    {finding.kind}
                  </Badge>
                </th>
                <td className="p-3">
                  {technology ? (
                    <Link
                      href={`/corporate/technologies/${technology.technology_id}`}
                      className="underline underline-offset-4"
                    >
                      {technology.name}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="p-3">
                  <span className="text-muted-foreground">
                    {classification(finding.technology_id) ?? "—"}
                  </span>
                </td>
                <td className="p-3">
                  {finding.version ? (
                    <>
                      <code className="font-mono text-xs break-all">{finding.version}</code>
                      <span className="text-muted-foreground ml-2 text-xs">
                        {versionKindLabel[finding.version_kind]}
                      </span>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="p-3">
                  <EvidenceSummary finding={finding} />
                </td>
                <td className="p-3">
                  <Badge
                    variant={
                      finding.state === "resolved"
                        ? "secondary"
                        : finding.state === "candidate"
                          ? "outline"
                          : "warning"
                    }
                  >
                    {scans(`findingState.${finding.state}`)}
                  </Badge>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EvidenceSummary({ finding }: { finding: TechnologyScanFinding }) {
  const first = finding.evidence[0];
  if (!first) return <span className="text-muted-foreground">—</span>;
  const label = first.path ?? first.reference ?? first.source;
  return (
    <span className="font-mono text-xs break-all">
      {label}
      {finding.evidence.length > 1 && ` +${finding.evidence.length - 1}`}
    </span>
  );
}

function FindingReview({
  finding,
  technologies,
  categories,
  areas,
  baseVersion,
  canUpdate,
  ...authority
}: GovernanceAuthority & {
  finding: TechnologyScanFinding;
  technologies: TechnologyView[];
  categories: CategoryView[] | null;
  areas: AreaView[] | null;
  baseVersion: string | null;
  canUpdate: boolean;
}) {
  const t = useTranslations("technology");
  const scans = useTranslations("technology.scans");
  const columns = useTranslations("technology.scans.columns");
  const kinds = useTranslations("technology.scans.versionKind");
  const versionKindLabel = {
    unknown: kinds("unknown"),
    declared_range: kinds("declared_range"),
    observed_version: kinds("observed_version"),
  };
  const selectId = useId();
  const mutation = useGovernanceMutation(authority);
  const [chosen, setChosen] = useState<string | null>(null);
  const shownCandidate = chosen ?? finding.candidate_technology_id ?? "";

  function review(candidateId: string | null) {
    setChosen(candidateId ?? "");
    mutation.save(
      `/v1/corporate/organizations/${authority.organizationId}/technology-unmapped-coordinates`,
      { kind: finding.kind, coordinate: finding.coordinate, candidate_technology_id: candidateId },
      "PATCH",
      () => {},
    );
  }

  function apply() {
    if (!shownCandidate) return;
    const effect = [
      { kind: finding.kind, coordinate: finding.coordinate, technology_id: shownCandidate },
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
    <div className="space-y-4" aria-busy={mutation.busy}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{finding.kind}</Badge>
        {finding.context && <Badge variant="outline">{t(`values.${finding.context}`)}</Badge>}
        <Badge variant={finding.state === "resolved" ? "secondary" : "warning"}>
          {scans(`findingState.${finding.state}`)}
        </Badge>
      </div>
      {finding.version && (
        <p className="text-sm">
          {t("version")}: <code className="font-mono break-all">{finding.version}</code>{" "}
          <span className="text-muted-foreground">({versionKindLabel[finding.version_kind]})</span>
        </p>
      )}
      {finding.evidence.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">{columns("evidence")}</h3>
          <ul className="space-y-1 text-xs">
            {finding.evidence.map((item, index) => (
              <li key={index} className="border-border border-l-2 pl-3">
                <code className="font-mono break-all">
                  {item.path ?? item.reference ?? item.source}
                </code>
                {item.confidence !== null && item.confidence !== undefined && (
                  <span className="text-muted-foreground ml-2">
                    {Math.round(item.confidence * 100)}%
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {canUpdate && finding.state !== "resolved" && (
        <div className="space-y-3">
          <div className="space-y-1">
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
      {canUpdate && <CreateSections categories={categories} areas={areas} {...authority} />}
      <p className="text-muted-foreground text-xs">
        <Link href="/corporate/technology-mappings" className="underline underline-offset-4">
          {t("mappingTitle")}
        </Link>
      </p>
      {mutation.message && (
        <p role="status" className="text-sm">
          {mutation.message}
        </p>
      )}
    </div>
  );
}

function CreateSections({
  categories,
  areas,
  ...authority
}: GovernanceAuthority & {
  categories: CategoryView[] | null;
  areas: AreaView[] | null;
}) {
  const t = useTranslations("technology");
  const authorityProps = {
    organizationId: authority.organizationId,
    authorizationRevision: String(authority.authorizationRevision),
    csrfToken: authority.csrfToken,
  };
  return (
    <>
      <details className="space-y-3">
        <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
          {t("mappingCreateTechnology")}
        </summary>
        <TechnologyRegistryCreate
          kind="technology"
          categories={categories}
          areas={areas}
          {...authorityProps}
        />
      </details>
      <details className="space-y-3">
        <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
          {t("createCategory")}
        </summary>
        <TechnologyRegistryCreate
          kind="category"
          categories={null}
          areas={areas}
          {...authorityProps}
        />
      </details>
      <details className="space-y-3">
        <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
          {t("areas.create")}
        </summary>
        <TechnologyRegistryCreate kind="area" categories={null} {...authorityProps} />
      </details>
    </>
  );
}
