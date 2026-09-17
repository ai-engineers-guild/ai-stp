import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { CorporateRichEditor } from "@/components/organisms/corporate-rich-editor";
import { readCorporateContext } from "@/lib/api/corporate";
import { readCorporatePresentation } from "@/lib/api/corporate-detail";
import { readTechnologyDetail } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";

export default async function TechnologyPresentationEditPage({
  params,
}: {
  params: Promise<{ locale: string; technologyId: string }>;
}) {
  const { locale, technologyId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technologies/${technologyId}/edit`);
  const session = (await sessionCookieValue()) ?? "";
  const workspace = await readCorporateContext(session);
  if (!workspace) notFound();
  const presentation = await readCorporatePresentation(
    session,
    workspace.organization.organization_id,
    "technologies",
    technologyId,
    workspace.organization.authorization_revision,
  );
  const detail = await readTechnologyDetail(
    session,
    workspace.organization.organization_id,
    technologyId,
  );
  if (!presentation?.can_edit || !detail) notFound();
  const corporate = await getTranslations("corporate");
  const technology = await getTranslations("technology");
  const detailHref = `/corporate/technologies/${technologyId}`;
  return (
    <article className="mx-auto w-full max-w-5xl min-w-0 space-y-6">
      <HistoryBackButton label={technology("backToTechnologies")} fallback={detailHref} />
      <h1 className="text-3xl font-medium tracking-tight [overflow-wrap:anywhere] sm:text-4xl">
        {corporate("editEntityPresentation", { name: presentation.name })}
      </h1>
      <CorporateRichEditor
        initial={presentation}
        organizationId={workspace.organization.organization_id}
        resource="technologies"
        resourceId={technologyId}
        csrfToken={(await readCsrfToken()) ?? ""}
        cancelHref={detailHref}
        entityUpdate={{
          kind: "technology",
          revision: detail.technology.revision,
          metadata: {
            name: detail.technology.name,
            description: detail.technology.description,
            category_ids: detail.technology.category_ids,
            aliases: detail.technology.aliases,
            icon_url: detail.technology.icon_url,
            official_urls: detail.technology.official_urls,
          },
        }}
      />
    </article>
  );
}
