import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { TechnologyMergeControls } from "@/components/organisms/technology-merge-controls";
import { CorporateEntityDetail } from "@/components/organisms/corporate-entity-detail";
import { CorporateTechnologyOwnerEditor } from "@/components/organisms/corporate-technology-owner-editor";
import { readCorporatePresentation } from "@/lib/api/corporate-detail";
import {
  TechnologyDecisionEditor,
  TechnologyTeamEditor,
} from "@/components/organisms/technology-governance-editors";
import {
  TechnologyRegistryCreate,
  TechnologyLifecycleControls,
} from "@/components/organisms/technology-registry-create";
import { readCorporateContext } from "@/lib/api/corporate";
import { readTechnologyDetail } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

type TechnologyDetail = NonNullable<Awaited<ReturnType<typeof readTechnologyDetail>>>;
type GovernanceMutation = {
  organizationId: string;
  csrfToken: string;
  authorizationRevision: string;
};

// eslint-disable-next-line max-lines-per-function -- this page composes the existing technology controls
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
  const common = await getTranslations("common");
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
  const { technology, categories, permissions, decision, teams } = detail;
  const mutation = {
    organizationId,
    csrfToken: (await readCsrfToken()) ?? "",
    authorizationRevision: permissions.authorization_revision,
  };
  const presentation = await readCorporatePresentation(
    session,
    organizationId,
    "technologies",
    technologyId,
    workspace.organization.authorization_revision,
  );
  if (presentation) {
    const owner = detail.members.find(
      (member) => member.account_id === presentation.owner_account_id,
    );
    presentation.owner = owner
      ? { kind: "employee", id: owner.account_id, name: owner.display_name ?? h("employees") }
      : null;
  }
  const canAssignOwner =
    workspace.capabilities.includes("member.update") ||
    workspace.teams.some(
      (team) =>
        team.state === "active" &&
        team.members.some(
          (member) => member.account_id === workspace.member.account_id && member.role === "lead",
        ),
    );
  return (
    <div className="min-w-0 space-y-8">
      <header className="space-y-3">
        <HistoryBackButton label={t("back")} fallback="/corporate/technologies" />
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{technology.name}</h1>
        <p className="text-muted-foreground">{t(`values.${technology.lifecycle}`)}</p>
      </header>
      <CorporateEntityDetail
        presentation={presentation}
        description={technology.description}
        organizationId={organizationId}
        resource="technologies"
        resourceId={technologyId}
        csrfToken={mutation.csrfToken}
        rail={
          presentation && canAssignOwner && !technology.redirect_id ? (
            <CorporateTechnologyOwnerEditor
              organizationId={organizationId}
              technologyId={technologyId}
              ownerAccountId={presentation.owner_account_id}
              revision={presentation.revision}
              authorizationRevision={workspace.organization.authorization_revision}
              csrfToken={mutation.csrfToken}
              members={detail.members}
            />
          ) : null
        }
      >
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
        <TechnologyProjectsPanel
          projects={detail.projects}
          labels={{ title: h("projects"), empty: h("empty"), unavailable: t("unavailable") }}
        />
        {technology.redirect_id && (
          <Link
            href={`/corporate/technologies/${technology.redirect_id}`}
            className="inline-flex min-h-11 items-center underline underline-offset-4"
          >
            {t("mergedIdentity")}
          </Link>
        )}
        {permissions.capabilities.includes("technology.update") && !technology.redirect_id && (
          <details>
            <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
              {common("edit")}
            </summary>
            <TechnologyRegistryCreate
              kind="technology"
              initial={technology}
              categories={categories?.items ?? null}
              {...mutation}
            />
          </details>
        )}
        <TechnologyLifecycleControls
          technology={technology}
          capabilities={permissions.capabilities}
          {...mutation}
        />
        <TechnologyGovernancePanel
          technologyId={technology.technology_id}
          permissions={permissions}
          decision={decision}
          teams={teams}
          mutation={mutation}
          availableTeams={detail.availableTeams}
          members={detail.members}
          labels={{ governance: t("governance"), responsibilities: t("responsibilities") }}
        />
        {permissions.capabilities.includes("technology.merge") && !technology.redirect_id && (
          <details>
            <summary className="min-h-11 cursor-pointer py-3 text-sm">{t("mergeTitle")}</summary>
            <TechnologyMergeControls technology={technology} {...mutation} />
          </details>
        )}
      </CorporateEntityDetail>
    </div>
  );
}

function TechnologyProjectsPanel({
  projects,
  labels,
}: Pick<TechnologyDetail, "projects"> & {
  labels: { title: string; empty: string; unavailable: string };
}) {
  if (!projects || projects.status === "empty" || projects.status === "loading") return null;
  if (projects.status === "error")
    return <StatePanel kind="error" title={labels.title} description={labels.unavailable} />;
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-medium">{labels.title}</h2>
      <ul className="divide-border divide-y">
        {projects.data.projects.map((project) => (
          <li key={project.project_id}>
            <Link
              href={`/corporate/projects/${project.project_id}`}
              className="inline-flex min-h-11 items-center underline underline-offset-4"
            >
              {project.name}
            </Link>
          </li>
        ))}
      </ul>
      {!projects.data.projects.length && (
        <p className="text-muted-foreground text-sm">{labels.empty}</p>
      )}
    </section>
  );
}

async function TechnologyGovernancePanel({
  technologyId,
  permissions,
  decision,
  teams,
  mutation,
  labels,
  availableTeams,
  members,
}: Pick<TechnologyDetail, "permissions" | "decision" | "teams" | "availableTeams" | "members"> & {
  technologyId: string;
  mutation: GovernanceMutation;
  labels: { governance: string; responsibilities: string };
}) {
  const t = await getTranslations("technology");
  const h = await getTranslations("hub");
  const common = await getTranslations("common");
  const canEditDecision = permissions.capabilities.some((capability) =>
    [
      "technology_decision.create",
      "technology_decision.update",
      "technology_decision.delete",
    ].includes(capability),
  );
  const canEditTeams = permissions.capabilities.some((capability) =>
    ["technology_team.create", "technology_team.update", "technology_team.delete"].includes(
      capability,
    ),
  );
  return (
    <>
      {decision?.status === "error" && (
        <StatePanel kind="error" title={labels.governance} description={t("unavailable")} />
      )}
      {teams?.status === "error" && (
        <StatePanel kind="error" title={labels.responsibilities} description={t("unavailable")} />
      )}
      {(decision?.status === "data" || decision?.status === "empty") && (
        <section className="space-y-4" aria-label={labels.governance}>
          <h2 className="text-2xl font-medium">{labels.governance}</h2>
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
                      href={`/corporate/members/${decision.data.lead_account_id}`}
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
          {canEditDecision && (
            <details>
              <summary className="min-h-11 cursor-pointer py-3 text-sm">{common("edit")}</summary>
              <TechnologyDecisionEditor
                technologyId={technologyId}
                {...(decision.status === "data" ? { initial: decision.data } : {})}
                capabilities={permissions.capabilities}
                employees={members.map((item) => ({
                  value: item.account_id,
                  label: item.display_name ?? h("employees"),
                }))}
                {...mutation}
              />
            </details>
          )}
        </section>
      )}
      {(teams?.status === "data" || canEditTeams) && (
        <section className="space-y-4" aria-label={labels.responsibilities}>
          <h2 className="text-2xl font-medium">{labels.responsibilities}</h2>
          <ul className="divide-border divide-y">
            {teams?.status === "data" &&
              teams.data.items
                .filter((team) => team.state === "current")
                .map((team) => (
                  <li key={team.relation_id} className="py-3">
                    <Link
                      href={`/corporate/teams/${team.team_id}`}
                      className="inline-flex min-h-11 items-center underline underline-offset-4"
                    >
                      {availableTeams.find((item) => item.team_id === team.team_id)?.name ??
                        h("teams")}
                    </Link>
                    {canEditTeams && (
                      <details>
                        <summary className="min-h-11 cursor-pointer py-3 text-sm">
                          {common("edit")}
                        </summary>
                        <TechnologyTeamEditor
                          technologyId={technologyId}
                          initial={team}
                          capabilities={permissions.capabilities}
                          teams={availableTeams.map((item) => ({
                            value: item.team_id,
                            label: item.name,
                          }))}
                          {...mutation}
                        />
                      </details>
                    )}
                  </li>
                ))}
          </ul>
          {permissions.capabilities.includes("technology_team.create") && (
            <details>
              <summary className="min-h-11 cursor-pointer py-3 text-sm">{h("linkTeam")}</summary>
              <TechnologyTeamEditor
                technologyId={technologyId}
                capabilities={permissions.capabilities}
                teams={availableTeams.map((item) => ({ value: item.team_id, label: item.name }))}
                relations={teams?.status === "data" ? teams.data.items : []}
                {...mutation}
              />
            </details>
          )}
        </section>
      )}
    </>
  );
}
