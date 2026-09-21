import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { CorporateEntityDetail } from "@/components/organisms/corporate-entity-detail";
import { CorporateCatalogAssignments } from "@/components/organisms/corporate-catalog-assignments";
import { LocalizedResourceDeleteMenuItem } from "@/components/organisms/localized-corporate-resource-actions";
import { CorporateRelationSection } from "@/components/organisms/corporate-relation-section";
import { relationSectionLabels } from "@/components/organisms/corporate-directory-types";
import { readCorporatePresentation } from "@/lib/api/corporate-detail";
import { readCorporateCatalogAssignments, readCorporateContext } from "@/lib/api/corporate";
import { readTechnologyDetail } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

type TechnologyDetail = NonNullable<Awaited<ReturnType<typeof readTechnologyDetail>>>;
export default async function TechnologyDetailPage({
  params,
}: {
  params: Promise<{ locale: string; technologyId: string }>;
}) {
  const { locale, technologyId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technologies/${technologyId}`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const h = await getTranslations("hub");
  const workspace = await readCorporateContext(session);
  if (!workspace || !/^technology_[0-9A-HJKMNP-TV-Z]{26}$/.test(technologyId))
    return <StatePanel kind="empty" title={t("registry")} description={t("notPermitted")} />;
  const organizationId = workspace.organization.organization_id;
  let detail;
  try {
    detail = await readTechnologyDetail(session, organizationId, technologyId);
  } catch {
    return <StatePanel kind="error" title={t("registry")} description={t("registryUnavailable")} />;
  }
  if (!detail)
    return <StatePanel kind="empty" title={t("registry")} description={t("notPermitted")} />;
  const { technology, categories, decision, teams } = detail;
  const assignments = await readCorporateCatalogAssignments(
    session,
    organizationId,
    "technology",
    technologyId,
  );
  const presentation = await readCorporatePresentation(
    session,
    organizationId,
    "technologies",
    technologyId,
    workspace.organization.authorization_revision,
  );
  if (presentation) {
    const ownerAccountId = presentation.owner_account_id ?? technology.owner_account_id;
    const owner = detail.members.find((member) => member.account_id === ownerAccountId);
    presentation.owner = owner
      ? { kind: "employee", id: owner.account_id, name: owner.display_name ?? h("employees") }
      : null;
  }
  return (
    <div className="min-w-0 space-y-8">
      <HistoryBackButton label={t("backToTechnologies")} fallback="/corporate/technologies" />
      <CorporateEntityDetail
        presentation={presentation}
        description={technology.description}
        resource="technologies"
        resourceId={technologyId}
        title={technology.name}
        adminMenu={
          technology.available_actions.includes("technology.delete") ? (
            <LocalizedResourceDeleteMenuItem
              csrfToken={(await readCsrfToken()) ?? ""}
              organizationId={organizationId}
              authorizationRevision={workspace.organization.authorization_revision}
              resource="technologies"
              resourceId={technologyId}
              revision={technology.revision}
            />
          ) : null
        }
        {...(technology.lifecycle === "active"
          ? {}
          : { state: t(`values.${technology.lifecycle}`) })}
      >
        <TechnologyTechnicalDetails technology={technology} categories={categories} t={t} />
        <TechnologyProjectsPanel
          projects={detail.projects}
          technologyId={technologyId}
          labels={{
            title: h("projects"),
            empty: h("empty"),
            unavailable: t("unavailable"),
            relation: relationSectionLabels(h),
          }}
        />
        <CorporateCatalogAssignments
          items={assignments.items}
          organizationId={organizationId}
          subjectKind="technology"
          subjectId={technologyId}
          authorizationRevision={workspace.organization.authorization_revision}
          csrfToken={(await readCsrfToken()) ?? ""}
          canManage={workspace.capabilities.includes("catalog_object.assign")}
        />
        {technology.redirect_id && (
          <Link
            href={`/corporate/technologies/${technology.redirect_id}`}
            className="inline-flex min-h-11 items-center underline underline-offset-4"
          >
            {t("mergedIdentity")}
          </Link>
        )}
        <TechnologyGovernancePanel
          technologyId={technologyId}
          decision={decision}
          teams={teams}
          availableTeams={detail.availableTeams}
          members={detail.members}
          labels={{ governance: t("governance"), responsibilities: t("responsibilities") }}
        />
      </CorporateEntityDetail>
    </div>
  );
}

function TechnologyTechnicalDetails({
  technology,
  categories,
  t,
}: {
  technology: TechnologyDetail["technology"];
  categories: TechnologyDetail["categories"];
  t: (key: string) => string;
}) {
  return (
    <DetailAccordion title={t("technicalDetails")}>
      <dl className="grid gap-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">{t("categories")}</dt>
          <dd className="mt-1">
            {technology.category_ids.map((id) => {
              const category = categories?.items.find((item) => item.category_id === id);
              return category ? (
                <Link
                  key={id}
                  href={`/corporate/categories/${id}`}
                  className="mr-3 underline underline-offset-4"
                >
                  {category.name}
                </Link>
              ) : null;
            })}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("aliases")}</dt>
          <dd className="mt-1">
            {technology.aliases.length ? technology.aliases.join(", ") : t("values.none")}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("officialUrls")}</dt>
          <dd>
            <ul>
              {technology.official_urls.map((url) => (
                <li key={url}>
                  <a
                    href={url}
                    rel="noopener noreferrer"
                    className="inline-flex min-h-11 max-w-full items-center break-all underline underline-offset-4"
                  >
                    {url}
                  </a>
                </li>
              ))}
            </ul>
          </dd>
        </div>
        {technology.icon_url && (
          <div>
            <dt className="text-muted-foreground">{t("iconUrl")}</dt>
            <dd>
              <a
                href={technology.icon_url}
                rel="noopener noreferrer"
                className="inline-flex min-h-11 max-w-full items-center break-all underline underline-offset-4"
              >
                {technology.icon_url}
              </a>
            </dd>
          </div>
        )}
      </dl>
    </DetailAccordion>
  );
}

function TechnologyProjectsPanel({
  projects,
  technologyId,
  labels,
}: Pick<TechnologyDetail, "projects"> & { technologyId: string } & {
  labels: {
    title: string;
    empty: string;
    unavailable: string;
    relation: ReturnType<typeof relationSectionLabels>;
  };
}) {
  if (!projects || projects.status === "empty" || projects.status === "loading") return null;
  if (projects.status === "error")
    return <StatePanel kind="error" title={labels.title} description={labels.unavailable} />;
  return projects.data.projects.length ? (
    <CorporateRelationSection
      title={labels.title}
      resource="projects"
      references={projects.data.projects.map((project) => ({
        kind: "project" as const,
        id: project.project_id,
        name: project.name,
      }))}
      labels={labels.relation}
      api={{ resource: "projects", filters: { technology_ids: [technologyId] } }}
    />
  ) : (
    <DetailAccordion title={labels.title} summary="0">
      <p className="text-muted-foreground text-sm">{labels.empty}</p>
    </DetailAccordion>
  );
}

async function TechnologyGovernancePanel({
  decision,
  teams,
  technologyId,
  labels,
  availableTeams,
  members,
}: Pick<TechnologyDetail, "decision" | "teams" | "availableTeams" | "members"> & {
  technologyId: string;
  labels: { governance: string; responsibilities: string };
}) {
  const t = await getTranslations("technology");
  const h = await getTranslations("hub");
  const common = await getTranslations("common");
  return (
    <>
      {decision?.status === "error" && (
        <StatePanel kind="error" title={labels.governance} description={t("unavailable")} />
      )}
      {teams?.status === "error" && (
        <StatePanel kind="error" title={labels.responsibilities} description={t("unavailable")} />
      )}
      {(decision?.status === "data" || decision?.status === "empty") && (
        <DetailAccordion title={labels.governance}>
          {decision.status === "data" && (
            <dl className="grid gap-3 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">{t("adoption")}</dt>
                <dd>{t(`values.${decision.data.adoption}`)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">{t("approvedDecision")}</dt>
                <dd>{common(decision.data.approved ? "yes" : "no")}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">{t("responsibleLead")}</dt>
                <dd>
                  {decision.data.lead_account_id ? (
                    <Link
                      href={`/corporate/employees/${decision.data.lead_account_id}`}
                      className="inline-flex min-h-11 items-center underline underline-offset-4"
                    >
                      {members.find((item) => item.account_id === decision.data.lead_account_id)
                        ?.display_name ?? t("values.unknown")}
                    </Link>
                  ) : (
                    t("values.none")
                  )}
                </dd>
              </div>
            </dl>
          )}
        </DetailAccordion>
      )}
      {teams?.status === "data" &&
        (() => {
          const refs = teams.data.items
            .filter((team) => team.state === "current")
            .flatMap((team) => {
              const currentTeam = availableTeams.find((item) => item.team_id === team.team_id);
              return currentTeam
                ? [{ kind: "team" as const, id: currentTeam.team_id, name: currentTeam.name }]
                : [];
            });
          return refs.length ? (
            <CorporateRelationSection
              title={labels.responsibilities}
              resource="teams"
              references={refs}
              labels={relationSectionLabels(h)}
              api={{ resource: "teams", filters: { technology_ids: [technologyId] } }}
            />
          ) : null;
        })()}
    </>
  );
}
