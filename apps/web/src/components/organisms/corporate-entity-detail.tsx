import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { AvatarImage } from "@/components/atoms/avatar-image";
import { Badge } from "@/components/atoms/badge";
import { MarkdownDescription } from "@/components/molecules/markdown-description";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { EntityDetailHeader } from "@/components/organisms/entity-detail-header";
import { EntityDetailMenu } from "@/components/organisms/entity-detail-menu";
import {
  CorporateRelationSection,
  type CorporateRelationApi,
} from "@/components/organisms/corporate-relation-section";
import { ObjectDetailFrame } from "@/components/organisms/object-detail-frame";
import { ComponentMediaGallery } from "@/components/organisms/component-media-gallery";
import {
  corporateReferenceHref,
  type CorporatePresentation,
  type CorporateDetailResource,
  visibleCorporateState,
} from "@/lib/corporate-detail";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

// eslint-disable-next-line max-lines-per-function
export function CorporateEntityDetail({
  presentation,
  description,
  children,
  resource,
  resourceId,
  title,
  state,
  rail,
}: {
  presentation: CorporatePresentation | null;
  description: string;
  children: ReactNode;
  resource: CorporateDetailResource;
  resourceId: string;
  title: string;
  state?: string;
  rail?: ReactNode;
}) {
  const t = useTranslations("account");
  const h = useTranslations("hub");
  const c = useTranslations("common");
  const catalog = useTranslations("catalog");
  const objects = useTranslations("objects");
  const access = useTranslations("access");
  const corporate = useTranslations("corporate");
  const cli = useTranslations("cli");
  const canonicalResource = resource === "members" ? "employees" : resource;
  const detailHref = `/corporate/${canonicalResource}/${encodeURIComponent(resourceId)}`;
  const visibleState = visibleCorporateState(state);
  type RelationRef = CorporatePresentation["teams"][number];
  const relations: readonly (readonly [string, readonly RelationRef[]])[] = presentation
    ? [
        [h("teams"), presentation.teams],
        [h("technologies"), presentation.technologies],
        ...(resource === "members"
          ? []
          : ([[catalog("components"), presentation.components]] as const)),
        ...(resource === "members"
          ? []
          : ([
              [h("projects"), presentation.projects],
              [h("teamLeads"), presentation.leads],
            ] as const)),
      ]
    : [];
  return (
    <>
      <EntityDetailHeader
        icon={
          <AvatarImage
            src={presentation?.avatar_url ?? null}
            width={80}
            className="size-16 rounded-lg object-cover sm:size-20"
            fallback={<Icon name={resource === "members" ? "user" : "objects"} size="lg" />}
          />
        }
        title={presentation?.name ?? title}
        meta={visibleState ? <Badge variant="outline">{visibleState}</Badge> : null}
        menu={
          <EntityDetailMenu
            moreLabel={access("more")}
            editPresentationLabel={objects("editPresentation")}
            editPresentationHref={presentation?.can_edit ? `${detailHref}/edit` : undefined}
            entityId={resourceId}
            shareHref={detailHref}
            copyIdLabel={h("copyId")}
            shareLabel={h("share")}
            reportLabel={h("report")}
            reportTarget={`corporate:${canonicalResource}:${resourceId}`}
          />
        }
      />
      <ObjectDetailFrame
        description={
          <MarkdownDescription
            source={presentation?.description ?? description}
            heading={corporate("description")}
          />
        }
        main={
          <>
            {relations.map(([title, refs]) =>
              refs.length ? (
                <CorporateRelationSection
                  key={title}
                  title={title}
                  resource={
                    refs[0]?.kind === "employee"
                      ? "members"
                      : refs[0]?.kind === "component"
                        ? "components"
                        : refs[0]?.kind === "technology"
                          ? "technologies"
                          : refs[0]?.kind === "team"
                            ? "teams"
                            : "projects"
                  }
                  references={refs}
                  api={relationApi(resource, resourceId, refs[0]?.kind)}
                  labels={{
                    filters: h("filters"),
                    filterTitle: h("filterTitle"),
                    filterHint: h("filterHint"),
                    reset: h("clearFilters"),
                    close: h("closeFilters"),
                    search: h("search"),
                    apply: h("applyFilters"),
                    previous: h("previous"),
                    next: h("next"),
                    page: h("page"),
                    noMatches: h("noMatches"),
                    moreActions: h("moreActions"),
                    owner: h("owner"),
                    teams: h("teams"),
                    projects: h("projects"),
                    technologies: h("technologies"),
                    categories: h("categories"),
                    teamLeads: h("teamLeads"),
                    team: h("team"),
                    employee: h("employee"),
                    author: catalog("author"),
                    type: h("type"),
                    lead: h("lead"),
                    unknownEmployee: h("unknownEmployee"),
                    notAvailable: h("notAvailable"),
                  }}
                />
              ) : null,
            )}
            {children}
          </>
        }
        media={
          presentation?.media.length ? (
            <ComponentMediaGallery
              items={presentation.media}
              labels={{
                gallery: catalog("gallery"),
                open: t("profilePreview"),
                source: objects("source"),
                close: c("cancel"),
                previous: catalog("previousMedia"),
                next: catalog("nextMedia"),
                typeImage: catalog("mediaKindImage"),
                typeVideo: catalog("mediaKindVideo"),
                typeYoutube: catalog("mediaKindYoutube"),
              }}
            />
          ) : null
        }
        rail={
          <CorporateIdentityRail
            presentation={presentation}
            resource={resource}
            ownerLabel={h("owner")}
            operationalOwnerLabel={h("operationalOwner")}
            teamLeadsLabel={h("teamLeads")}
            emptyLabel={h("notAvailable")}
            contextBudgetLabel={catalog("contextBudgetTitle")}
            contextBudgetUnavailable={catalog("contextBudgetError")}
            cliTitle={cli("useTitle")}
            cliUnavailable={cli("cliUnavailable")}
          >
            {rail}
          </CorporateIdentityRail>
        }
      />
    </>
  );
}

function relationApi(
  resource: CorporateDetailResource,
  resourceId: string,
  relatedKind: "employee" | "component" | "technology" | "team" | "project" | "setup" | undefined,
): CorporateRelationApi | undefined {
  const relatedResource =
    relatedKind === "employee"
      ? "members"
      : relatedKind === "technology"
        ? "technologies"
        : relatedKind === "team"
          ? "teams"
          : relatedKind === "project"
            ? "projects"
            : null;
  if (!relatedResource) return undefined;
  if (
    resource === "projects" &&
    (relatedResource === "teams" || relatedResource === "technologies")
  ) {
    return { resource: relatedResource, filters: { project_ids: [resourceId] } } as const;
  }
  if (resource === "teams") {
    if (relatedResource === "members")
      return {
        resource: relatedResource,
        filters: { team_ids: [resourceId] },
        leadOnly: true,
      } as const;
    if (relatedResource === "projects" || relatedResource === "technologies") {
      return { resource: relatedResource, filters: { team_ids: [resourceId] } } as const;
    }
  }
  if (
    resource === "technologies" &&
    (relatedResource === "projects" || relatedResource === "teams")
  ) {
    return { resource: relatedResource, filters: { technology_ids: [resourceId] } } as const;
  }
  return undefined;
}

function CorporateIdentityRail({
  presentation,
  resource,
  ownerLabel,
  operationalOwnerLabel,
  teamLeadsLabel,
  emptyLabel,
  contextBudgetLabel,
  contextBudgetUnavailable,
  cliTitle,
  cliUnavailable,
  children,
}: {
  presentation: CorporatePresentation | null;
  resource: CorporateDetailResource;
  ownerLabel: string;
  operationalOwnerLabel: string;
  teamLeadsLabel: string;
  emptyLabel: string;
  contextBudgetLabel: string;
  contextBudgetUnavailable: string;
  cliTitle: string;
  cliUnavailable: string;
  children?: ReactNode;
}) {
  const subjects =
    resource === "teams" || resource === "members"
      ? (presentation?.leads ?? [])
      : presentation?.owner
        ? [presentation.owner]
        : [];
  const subjectLabel =
    resource === "projects"
      ? ownerLabel
      : resource === "technologies"
        ? operationalOwnerLabel
        : teamLeadsLabel;
  return (
    <>
      {presentation ? (
        <>
          <section className="border-border bg-card rounded-lg border p-5">
            <h2 className="text-sm font-medium">{subjectLabel}</h2>
            {subjects.length ? (
              <ul className="divide-border mt-2 divide-y">
                {subjects.map((ref) => (
                  <li key={`${ref.kind}:${ref.id}`}>
                    <Link
                      href={corporateReferenceHref(ref)}
                      className="inline-flex min-h-11 items-center font-medium underline underline-offset-4"
                    >
                      {ref.name}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground mt-2 text-sm">{emptyLabel}</p>
            )}
          </section>
          <DetailAccordion title={contextBudgetLabel} summary={contextBudgetUnavailable}>
            <p className="text-muted-foreground text-sm">{contextBudgetUnavailable}</p>
          </DetailAccordion>
          <DetailAccordion title={cliTitle} summary={cliUnavailable}>
            <p className="text-muted-foreground text-sm">{cliUnavailable}</p>
          </DetailAccordion>
          {presentation.links.length ? (
            <ul className="border-border bg-card space-y-2 rounded-lg border p-5">
              {presentation.links.map((link) => (
                <li key={link.url}>
                  <a
                    href={link.url}
                    rel="noopener noreferrer"
                    target="_blank"
                    className="inline-flex min-h-11 items-center break-all underline underline-offset-4"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
      {children}
    </>
  );
}
