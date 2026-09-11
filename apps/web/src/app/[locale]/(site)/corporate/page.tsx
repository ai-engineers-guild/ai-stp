import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { readCorporateWorkspace } from "@/lib/api/corporate";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

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
          kind="projects"
          openLabel={t("open")}
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
          kind="teams"
          openLabel={t("open")}
        />
      </div>

      {members && (
        <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
          <h2 className="text-xl font-medium">{t("members")}</h2>
          {members.items.length ? (
            <ul className="mt-4 space-y-2">
              {members.items.map((member) => (
                <li key={member.account_id} className="border-border rounded border">
                  <Link
                    href={`/corporate/members/${encodeURIComponent(member.account_id)}`}
                    className="focus-visible:ring-ring group flex min-h-14 items-center justify-between gap-3 rounded p-3 outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
                  >
                    <span>{member.display_name ?? member.account_id}</span>
                    <span className="text-muted-foreground flex items-center gap-2 text-sm">
                      {member.role}
                      <Icon
                        name="chevronRight"
                        size="sm"
                        className="transition-transform group-hover:translate-x-0.5"
                      />
                    </span>
                  </Link>
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
  kind,
  openLabel,
}: {
  title: string;
  empty: string;
  items: ReadonlyArray<{ id: string; name: string; state: string; revision: number }>;
  kind: "projects" | "teams";
  openLabel: string;
}) {
  return (
    <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
      <h2 className="text-xl font-medium">{title}</h2>
      {items.length ? (
        <ul className="mt-4 space-y-2">
          {items.map((item) => (
            <li key={item.id} className="border-border rounded border">
              <Link
                href={`/corporate/${kind}/${encodeURIComponent(item.id)}`}
                className="focus-visible:ring-ring group flex min-h-14 items-center justify-between gap-3 rounded p-3 outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
              >
                <span className="min-w-0 truncate">{item.name}</span>
                <span className="text-muted-foreground flex shrink-0 items-center gap-2 text-sm">
                  {item.state}
                  <span className="sr-only">{openLabel}</span>
                  <Icon
                    name="chevronRight"
                    size="sm"
                    className="transition-transform group-hover:translate-x-0.5"
                  />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground mt-4 text-sm">{empty}</p>
      )}
    </section>
  );
}
