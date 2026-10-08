"use client";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Select } from "@/components/atoms/select";
import { Textarea } from "@/components/atoms/textarea";

import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { displayCategoryIds } from "@/lib/technology-taxonomy";

import { Link } from "@/lib/i18n/navigation";

import { Icon } from "@/theme";

import {
  findingStatus,
  rowKey,
  type Draft,
  type TechnologyReviewState,
} from "@/lib/technology-review-state";
export function TechnologyFindingPanel({ state }: { state: TechnologyReviewState }) {
  const {
    w,
    s,
    mutation,
    scan,
    active,
    chosen,
    canUpdate,
    drafts,
    sourceIcon,
    apply,
    setDrafts,
    setEvidence,
  } = state;
  return (
    <>
      <aside
        className="technology-finding-panel"
        data-scan={scan ? true : undefined}
        aria-label={w("findingDetails")}
      >
        {active && chosen ? (
          <>
            <header className="flex items-center justify-between gap-3">
              <h2 className="min-w-0 text-2xl font-medium break-all">{active.coordinate}</h2>
              <Badge variant="secondary">
                {w(`findingState.${findingStatus(active, state.names)}`)}
              </Badge>
              <Button
                size="icon"
                variant="ghost"
                aria-label={w("evidence")}
                onClick={() => {
                  setEvidence(active);
                }}
              >
                <Icon name="more" size="sm" />
              </Button>
            </header>
            <section className="technology-panel-section">
              <h3>{w("basicInfo")}</h3>
              <dl className="technology-finding-info">
                {[
                  [w("found"), active.coordinate],
                  [w("type"), active.kind],
                  [w("project"), active.scan.project_name ?? active.scan.project_id],
                  [
                    w("source"),
                    <span key="source" className="flex items-center gap-2">
                      <Icon name={sourceIcon(active.scan.source)} size="sm" />
                      {s(`source.${active.scan.source}`)}
                    </span>,
                  ],
                  [
                    w("scan"),
                    <Link key="scan" href={`/corporate/technology-scans/${active.scan.scan_id}`}>
                      {active.scan.scan_id}
                    </Link>,
                  ],
                  ...(scan
                    ? [
                        [w("file"), active.evidence[0]?.path ?? "—"],
                        [w("reference"), active.evidence[0]?.reference ?? "—"],
                      ]
                    : []),
                  [w("versions"), active.version ?? "—"],
                ].map(([label, value], index) => (
                  <div key={index}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
                <div>
                  <dt>{w("evidence")}</dt>
                  <dd className="flex flex-wrap gap-2">
                    {active.evidence.map((entry, index) => (
                      <Button
                        key={index}
                        variant="outline"
                        className="h-auto min-h-8 px-2 text-xs"
                        onClick={() => {
                          setEvidence(active);
                        }}
                      >
                        <Icon name="code" size="sm" />
                        {entry.path ?? entry.reference ?? entry.source}
                      </Button>
                    ))}
                  </dd>
                </div>
              </dl>
            </section>
            <TechnologyFindingFields state={state} />
            {scan && (
              <div className="border-border border-t pt-3 text-xs">
                <h3 className="font-medium">{w("whatChanges")}</h3>
                <p className="text-muted-foreground">{w("changeExplanation")}</p>
              </div>
            )}
            {canUpdate && (
              <div className="technology-finding-actions flex flex-wrap gap-2">
                <Button
                  disabled={
                    mutation.busy ||
                    (chosen.review !== "rejected" &&
                      (!chosen.technology ||
                        state.names.get(chosen.technology)?.lifecycle === "archived"))
                  }
                  onClick={() => {
                    apply([active]);
                  }}
                >
                  <Icon name="play" size="sm" />
                  {w("confirmApply")}
                </Button>
                <Button
                  variant="outline"
                  disabled={mutation.busy || !drafts[rowKey(active)]}
                  onClick={() => {
                    setDrafts((current) => {
                      return Object.fromEntries(
                        Object.entries(current).filter(([key]) => key !== rowKey(active)),
                      );
                    });
                  }}
                >
                  <Icon name="refresh" size="sm" />
                  {w("resetFinding")}
                </Button>
                <Button
                  variant="ghost"
                  className="text-destructive"
                  disabled={mutation.busy}
                  onClick={() => {
                    apply([active], true);
                  }}
                >
                  <Icon name="trash" size="sm" />
                  {w("excludeFinding")}
                </Button>
              </div>
            )}
          </>
        ) : (
          <p className="text-muted-foreground p-4 text-sm">{w("chooseFinding")}</p>
        )}
      </aside>
    </>
  );
}
function selectFindingTechnology(state: TechnologyReviewState, values: string[]) {
  if (!state.active) return;
  const technology = values[0] ?? "";
  const record = state.names.get(technology);
  state.patch(state.active, {
    technology,
    review: technology ? "confirmed" : "open",
    category: record ? (displayCategoryIds(record)[0] ?? "") : "",
  });
}
export function TechnologyFindingFields({ state }: { state: TechnologyReviewState }) {
  const {
    technologies,
    categories,
    t,
    w,
    id,
    mutation,
    names,
    areaNames,
    active,
    chosen,
    category,
    canUpdate,
    patch,
    setCreate,
  } = state;
  if (!active || !chosen) return null;
  return (
    <>
      <section className="technology-panel-section">
        <h3>{w("mapping")}</h3>
        <fieldset disabled={!canUpdate || mutation.busy} className="space-y-2">
          <div className="technology-field">
            <Label>{t("technology")}</Label>
            <div>
              <SearchableMultiSelect
                name="technology"
                label={t("technology")}
                searchLabel={w("searchTechnology")}
                options={technologies
                  .filter((item) => item.lifecycle !== "archived")
                  .map((item) => ({ value: item.technology_id, label: item.name }))}
                selected={chosen.technology ? [chosen.technology] : []}
                multiple={false}
                modal
                emptyHint={
                  names.get(chosen.technology)?.lifecycle === "archived"
                    ? names.get(chosen.technology)?.name
                    : w("chooseTechnology")
                }
                closeLabel={t("close")}
                onChange={(values) => {
                  selectFindingTechnology(state, values);
                }}
              />
              {canUpdate && (
                <Button
                  variant="ghost"
                  className="text-primary technology-create-link h-auto min-h-8 p-0"
                  onClick={() => {
                    setCreate("technology");
                  }}
                >
                  <Icon name="plus" size="sm" />
                  {w("createTechnology")}
                </Button>
              )}
            </div>
          </div>
          <div className="technology-field">
            <Label htmlFor={`${id}-category`}>{w("category")}</Label>
            <div>
              <Select
                id={`${id}-category`}
                value={chosen.category}
                onChange={(e) => {
                  patch(active, { category: e.target.value });
                }}
              >
                <option value="">{w("chooseCategory")}</option>
                {category?.state === "archived" && (
                  <option value={category.category_id} disabled>
                    {category.name}
                  </option>
                )}
                {categories
                  ?.filter((item) => item.state !== "archived")
                  .map((item) => (
                    <option key={item.category_id} value={item.category_id}>
                      {item.name}
                    </option>
                  ))}
              </Select>
              {canUpdate && (
                <Button
                  variant="ghost"
                  className="text-primary technology-create-link h-auto min-h-8 p-0"
                  onClick={() => {
                    setCreate("category");
                  }}
                >
                  <Icon name="plus" size="sm" />
                  {t("createCategory")}
                </Button>
              )}
            </div>
          </div>
          <div className="technology-field">
            <Label htmlFor={`${id}-area`}>{w("area")}</Label>
            <div>
              <Input
                id={`${id}-area`}
                value={areaNames.get(category?.area_id ?? "") ?? ""}
                placeholder={w("derivedArea")}
                readOnly
                disabled
              />
              {canUpdate && (
                <Button
                  variant="ghost"
                  className="text-primary technology-create-link h-auto min-h-8 p-0"
                  onClick={() => {
                    setCreate("area");
                  }}
                >
                  <Icon name="plus" size="sm" />
                  {t("areas.create")}
                </Button>
              )}
            </div>
          </div>
          <div className="technology-field">
            <Label htmlFor={`${id}-review`}>{w("applicationStatus")}</Label>
            <Select
              id={`${id}-review`}
              value={chosen.review}
              onChange={(e) => {
                patch(active, { review: e.target.value as Draft["review"] });
              }}
            >
              <option value="open">{w("findingState.open")}</option>
              <option value="confirmed">{w("confirm")}</option>
              <option value="rejected">{w("exclude")}</option>
            </Select>
          </div>
          <div className="technology-field">
            <Label htmlFor={`${id}-comment`}>{w("comment")}</Label>
            <div>
              <Textarea
                id={`${id}-comment`}
                value={chosen.comment}
                maxLength={500}
                placeholder={w("commentPlaceholder")}
                onChange={(e) => {
                  patch(active, { comment: e.target.value });
                }}
              />
              <p className="text-muted-foreground mt-1 text-right text-xs">
                {chosen.comment.length}/500
              </p>
            </div>
          </div>
        </fieldset>
      </section>
    </>
  );
}
