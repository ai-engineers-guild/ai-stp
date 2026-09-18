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
        <ul className="min-w-0 space-y-3">
          {visible.map((item) =>
            item.summary ? (
              <ObjectCard
                key={`${item.kind}:${item.id}`}
                kind={item.kind}
                item={item.summary}
                href={`/catalog/${item.kind === "setup" ? "setups" : "components"}/${item.id}`}
                view="list"
                labels={catalogCardLabels}
              />
            ) : (
              <li key={`${item.kind}:${item.id}`} className="border-border rounded-lg border p-4">
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

const catalogCardLabels = {
  harness: "Harness",
  tags: "Tags",
  version: "Version",
  type: "Type",
  authorVerified: "Author verified",
  componentVerified: "Component verified",
  yes: "Yes",
  no: "No",
  publisher: "Publisher",
  publishedAt: "Published",
  likes: "Likes",
  componentKind: "Component",
  setupKind: "Setup",
  requirements: "Requirements",
  moreActions: "More actions",
  copyCli: "Copy CLI command",
  copyId: "Copy ID",
  copyUrl: "Copy URL",
  copied: "Copied",
  report: "Report component",
  reportSetup: "Report setup",
  publicVisibility: "Public",
  privateVisibility: "Private",
} as Parameters<typeof ObjectCard>[0]["labels"];

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
