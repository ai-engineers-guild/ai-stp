import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { CorporateCreateForm } from "@/components/organisms/corporate-create-form";
import { readCorporateCreateOptions } from "@/lib/api/corporate-create";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

export async function CorporateCreatePage({
  resource,
  locale,
}: {
  resource: "members" | "teams" | "projects";
  locale: string;
}) {
  const routeResource = resource === "members" ? "employees" : resource;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/${routeResource}/new`);
  const token = (await sessionCookieValue()) ?? "";
  const data = await readCorporateCreateOptions(token);
  if (!data) notFound();
  const capability = resource === "members" ? "member.create" : `${resource.slice(0, -1)}.create`;
  if (!data.context.capabilities.includes(capability)) notFound();
  const t = await getTranslations("hub");
  const c = await getTranslations("corporate");
  const option = (id: string, name: string) => ({ value: id, label: name });
  return (
    <div className="min-w-0 space-y-6">
      <header className="space-y-2">
        <Link
          href={`/corporate/${routeResource}`}
          className="text-primary text-sm underline underline-offset-4"
        >
          {c("backToWorkspace")}
        </Link>
        <h1 className="text-4xl font-medium tracking-tight">
          {t(
            resource === "members"
              ? "addEmployee"
              : resource === "teams"
                ? "addTeam"
                : "addProject",
          )}
        </h1>
      </header>
      <CorporateCreateForm
        resource={resource}
        organizationId={data.context.organization.organization_id}
        authorizationRevision={data.context.organization.authorization_revision}
        csrfToken={(await readCsrfToken()) ?? ""}
        roles={data.roles.length ? data.roles.map((role) => role.name) : ["staff"]}
        teams={data.teams.map((team) => option(team.team_id, team.name))}
        employees={data.employees.map((employee) => option(employee.id, employee.name))}
        projects={data.projects.map((project) => option(project.project_id, project.name))}
        technologies={data.technologies.map((technology) => option(technology.id, technology.name))}
        jobTitles={data.jobTitles.map((title) => option(title.id, title.name))}
      />
    </div>
  );
}
