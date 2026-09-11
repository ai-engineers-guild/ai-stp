import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

type PageProps = { params: Promise<{ locale: string }> };

export default async function CorporatePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate`);
  const t = await getTranslations("corporate");
  const tc = await getTranslations("common");

  let workspace;
  try {
    workspace = await readCorporateWorkspace((await sessionCookieValue()) ?? "");
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }
  if (!workspace) {
    return <StatePanel kind="empty" title={t("emptyTitle")} description={t("emptyBody")} />;
  }

  const { context, members } = workspace;
  const canManageMembers = context.capabilities.includes("member.list");
  const canManageProjects = context.capabilities.includes("project.create");

  return (
    <div className="min-w-0 space-y-8">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
            {context.organization.display_name}
          </h1>
          <Badge variant="secondary">{context.member.role}</Badge>
        </div>
        <p className="text-muted-foreground">{t("subtitle")}</p>
      </header>

      <div className="grid gap-5 lg:grid-cols-2">
        <CorporateList
          title={t("projects")}
          empty={t("noProjects")}
          items={context.projects.map((item) => ({
            id: item.project_id,
            name: item.name,
            state: item.state,
            revision: item.revision,
          }))}
          labels={{ id: t("id"), revision: t("revision") }}
        />
        <CorporateList
          title={t("teams")}
          empty={t("noTeams")}
          items={context.teams.map((item) => ({
            id: item.team_id,
            name: item.name,
            state: item.state,
            revision: item.revision,
          }))}
          labels={{ id: t("id"), revision: t("revision") }}
        />
      </div>

      {members && (
        <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
          <h2 className="text-xl font-medium">{t("members")}</h2>
          {members.items.length ? (
            <ul className="mt-4 space-y-2">
              {members.items.map((member) => (
                <li key={member.account_id} className="border-border rounded border p-3">
                  <details>
                    <summary className="flex cursor-pointer list-none justify-between gap-3">
                      <span>{member.display_name ?? member.account_id}</span>
                      <span className="text-muted-foreground text-sm">{member.role}</span>
                    </summary>
                    <dl className="text-muted-foreground mt-3 grid gap-1 text-xs sm:grid-cols-3">
                      <div>
                        <dt>{t("id")}</dt>
                        <dd className="break-all">{member.account_id}</dd>
                      </div>
                      <div>
                        <dt>{t("state")}</dt>
                        <dd>{member.state}</dd>
                      </div>
                      <div>
                        <dt>{t("revision")}</dt>
                        <dd>{member.revision}</dd>
                      </div>
                    </dl>
                  </details>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground mt-4 text-sm">{t("noMembers")}</p>
          )}
        </section>
      )}

      {(canManageMembers || canManageProjects) && (
        <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
          <h2 className="text-xl font-medium">{t("administration")}</h2>
          <p className="text-muted-foreground mt-2 text-sm">
            {canManageMembers ? t("membersAllowed") : t("projectsAllowed")}
          </p>
        </section>
      )}
    </div>
  );
}

function CorporateList({
  title,
  empty,
  items,
  labels,
}: {
  title: string;
  empty: string;
  items: ReadonlyArray<{ id: string; name: string; state: string; revision: number }>;
  labels: { id: string; revision: string };
}) {
  return (
    <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
      <h2 className="text-xl font-medium">{title}</h2>
      {items.length ? (
        <ul className="mt-4 space-y-2">
          {items.map((item) => (
            <li key={item.name} className="border-border flex justify-between rounded border p-3">
              <details className="min-w-0 flex-1">
                <summary className="cursor-pointer list-none">{item.name}</summary>
                <dl className="text-muted-foreground mt-2 grid gap-1 text-xs">
                  <div>
                    <dt>{labels.id}</dt>
                    <dd className="break-all">{item.id}</dd>
                  </div>
                  <div>
                    <dt>{labels.revision}</dt>
                    <dd>{item.revision}</dd>
                  </div>
                </dl>
              </details>
              <span className="text-muted-foreground ml-3 text-sm">{item.state}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground mt-4 text-sm">{empty}</p>
      )}
    </section>
  );
}
