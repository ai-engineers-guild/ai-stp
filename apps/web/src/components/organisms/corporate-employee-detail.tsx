"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { ObjectCard } from "@/components/organisms/object-card";
import type { CorporateEmployeeContent } from "@/lib/api/corporate-employee";
import { Link } from "@/lib/i18n/navigation";
import type { CorporateEmployeeDetailLabels } from "@/components/organisms/corporate-employee-labels";

export function CorporateEmployeeDetail({
  content,
  labels,
}: {
  content: Pick<
    CorporateEmployeeContent,
    "publicProfile" | "components" | "setups" | "technologies"
  >;
  labels: CorporateEmployeeDetailLabels;
}) {
  return (
    <div className="min-w-0 space-y-6">
      <EmployeeCatalog content={content} labels={labels} />
      <EmployeeTechnologies state={content.technologies} labels={labels} />
    </div>
  );
}

function EmployeeTechnologies({
  state,
  labels,
}: {
  state: CorporateEmployeeContent["technologies"];
  labels: CorporateEmployeeDetailLabels;
}) {
  if (state.status === "data") return null;
  if (state.status === "noaccess") {
    return <ReadState title={labels.technologies} message={labels.noAccess} state="noaccess" />;
  }
  if (state.status === "error") {
    return (
      <StatePanel
        kind="error"
        title={labels.technologies}
        description={labels.technologiesUnavailable}
      />
    );
  }
  return <ReadState title={labels.technologies} message={labels.noTechnologies} state="empty" />;
}

function EmployeeCatalog({
  content,
  labels,
}: {
  content: Pick<CorporateEmployeeContent, "components" | "setups">;
  labels: CorporateEmployeeDetailLabels;
}) {
  const t = useTranslations("hub");
  const tc = useTranslations("catalog");
  const common = useTranslations("common");
  const [page, setPage] = useState(0);
  const states = [content.components, content.setups];
  const items = states.flatMap((state) => (state.status === "data" ? state.data : []));
  const title =
    labels.catalogItems ??
    (items.some((item) => item.kind === "setup")
      ? labels.authoredSetups
      : labels.authoredComponents);
  if (items.length) {
    const pageCount = Math.ceil(items.length / 10);
    const visible = items.slice(page * 10, (page + 1) * 10);
    return (
      <DetailAccordion title={title} summary={`${items.length}`} defaultOpen>
        <ul className="border-border divide-border grid min-w-0 divide-y overflow-hidden rounded-lg border">
          {visible.map((item) =>
            item.summary ? (
              <li key={`${item.kind}:${item.id}`} className="min-w-0">
                <ObjectCard
                  kind={item.kind}
                  item={item.summary}
                  href={`/catalog/${item.kind === "setup" ? "setups" : "components"}/${item.id}`}
                  view="list"
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
                    authorVerified: tc("authorVerified"),
                    componentVerified: tc("componentVerified"),
                    yes: common("yes"),
                    no: common("no"),
                    publicVisibility: tc("public"),
                    privateVisibility: tc("private"),
                  }}
                />
              </li>
            ) : (
              <li key={`${item.kind}:${item.id}`} className="min-w-0 px-4 py-3">
                <Link
                  href={`/catalog/${item.kind === "setup" ? "setups" : "components"}/${item.id}`}
                  className="font-medium underline underline-offset-4"
                >
                  {item.name}
                </Link>
              </li>
            ),
          )}
        </ul>
        {pageCount > 1 ? (
          <nav
            className="border-border mt-4 flex items-center justify-between gap-3 border-t pt-4"
            aria-label={title}
          >
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => {
                setPage((value) => Math.max(0, value - 1));
              }}
            >
              {t("previous")}
            </Button>
            <span className="text-muted-foreground text-sm">
              {t("page")} {page + 1} / {pageCount}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={page === pageCount - 1}
              onClick={() => {
                setPage((value) => Math.min(pageCount - 1, value + 1));
              }}
            >
              {t("next")}
            </Button>
          </nav>
        ) : null}
      </DetailAccordion>
    );
  }
  if (states.some((state) => state.status === "error")) {
    return <StatePanel kind="error" title={title} description={labels.componentsUnavailable} />;
  }
  if (states.some((state) => state.status === "noaccess")) {
    return <ReadState title={title} message={labels.noAccess} state="noaccess" />;
  }
  return (
    <ReadState title={title} message={labels.noCatalogItems ?? labels.noComponents} state="empty" />
  );
}

function ReadState({
  title,
  message,
  state,
}: {
  title: string;
  message: string;
  state: "empty" | "noaccess";
}) {
  return (
    <DetailAccordion title={title} summary="0">
      <p className="text-muted-foreground mt-3 text-sm" data-state={state}>
        {message}
      </p>
    </DetailAccordion>
  );
}
