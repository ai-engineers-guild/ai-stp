import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound, permanentRedirect } from "next/navigation";

import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateRichEditor } from "@/components/organisms/corporate-rich-editor";
import { readCorporateResource } from "@/lib/api/corporate";
import { readCorporatePresentation } from "@/lib/api/corporate-detail";
import { readProjectTechnologyDetail } from "@/lib/api/technology";
import { ApiError } from "@/lib/api/errors";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

type PageProps = {
  params: Promise<{ locale: string; resource: string; resourceId: string }>;
};

export default async function CorporatePresentationEditPage({ params }: PageProps) {
  const { locale, resource, resourceId } = await params;
  if (resource === "members") {
    permanentRedirect(`/${locale}/corporate/employees/${encodeURIComponent(resourceId)}`);
  }
  if (resource !== "projects" && resource !== "teams") notFound();
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/${resource}/${resourceId}/edit`);
  const session = (await sessionCookieValue()) ?? "";
  const common = await getTranslations("common");
  const corporate = await getTranslations("corporate");
  const hub = await getTranslations("hub");
  let workspace;
  let presentation;
  let entityUpdate;
  try {
    workspace = await readCorporateResource(session, resource, resourceId);
    if (!workspace) notFound();
    if (resource === "projects") {
      const detail = await readProjectTechnologyDetail(
        session,
        workspace.organization.organization_id,
        resourceId,
      );
      if (!detail) notFound();
      entityUpdate = {
        kind: "project" as const,
        revision: detail.project.revision,
        state: detail.project.state,
      };
    } else {
      if (!workspace.team) notFound();
      entityUpdate = {
        kind: "team" as const,
        revision: workspace.team.revision,
        state: workspace.team.state,
        description: workspace.team.description,
      };
    }
    presentation = await readCorporatePresentation(
      session,
      workspace.organization.organization_id,
      resource,
      resourceId,
      workspace.context.organization.authorization_revision,
    );
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE")
      return (
        <StatePanel kind="error" title={common("error")} description={common("apiUnavailable")} />
      );
    throw error;
  }
  if (!presentation?.can_edit) notFound();
  const detailHref = `/corporate/${resource}/${resourceId}`;
  const backLabel = resource === "teams" ? hub("backToTeams") : hub("backToProjects");
  return (
    <article className="mx-auto w-full max-w-5xl min-w-0 space-y-6">
      <HistoryBackButton label={backLabel} fallback={detailHref} />
      <h1 className="text-3xl font-medium tracking-tight [overflow-wrap:anywhere] sm:text-4xl">
        {corporate("editEntityPresentation", { name: presentation.name })}
      </h1>
      <CorporateRichEditor
        initial={presentation}
        organizationId={workspace.organization.organization_id}
        resource={resource}
        resourceId={resourceId}
        csrfToken={(await readCsrfToken()) ?? ""}
        cancelHref={detailHref}
        entityUpdate={entityUpdate}
      />
    </article>
  );
}
