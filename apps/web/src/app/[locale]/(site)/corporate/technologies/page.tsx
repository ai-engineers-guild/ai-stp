import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { TechnologyRegistryCreate } from "@/components/organisms/technology-registry-create";
import { readCorporateContext } from "@/lib/api/corporate";
import { readTechnologyRegistry } from "@/lib/api/technology";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";

export default async function TechnologyRegistryPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/technologies`);
  const session = (await sessionCookieValue()) ?? "";
  const t = await getTranslations("technology");
  const search = (await searchParams).query;
  const query = typeof search === "string" ? search : undefined;
  const workspace = await readCorporateContext(session);
  if (!workspace)
    return <StatePanel kind="empty" title={t("registry")} description={t("registryEmpty")} />;
  const organizationId = workspace.organization.organization_id;
  let registry;
  try {
    registry = await readTechnologyRegistry(session, organizationId, query);
  } catch {
    return <StatePanel kind="error" title={t("registry")} description={t("registryUnavailable")} />;
  }
  const { permissions, technologies, categories } = registry;
  const mutation = {
    organizationId,
    authorizationRevision: permissions.authorization_revision,
    csrfToken: (await readCsrfToken()) ?? "",
    categories: categories?.items ?? null,
  };
  return (
    <div className="min-w-0 space-y-8">
      <header className="space-y-3">
        <Link
          href="/corporate"
          className="inline-flex min-h-11 items-center underline underline-offset-4"
        >
          {t("back")}
        </Link>
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">{t("registry")}</h1>
        <p className="text-muted-foreground max-w-prose">{t("registryDescription")}</p>
        {permissions.capabilities.includes("landscape.read") && (
          <Link
            href="/corporate/technology-landscape"
            className="inline-flex min-h-11 items-center underline underline-offset-4"
          >
            {t("title")}
          </Link>
        )}
      </header>
      {permissions.capabilities.includes("technology.list") && (
        <form method="get" className="max-w-prose space-y-3">
          <Label htmlFor="registry-query">{t("search")}</Label>
          <Input id="registry-query" name="query" maxLength={200} defaultValue={query} />
          <Button size="lg" type="submit">
            {t("apply")}
          </Button>
        </form>
      )}
      {permissions.capabilities.includes("technology.create") && (
        <details>
          <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
            {t("createTechnology")}
          </summary>
          <TechnologyRegistryCreate kind="technology" {...mutation} />
        </details>
      )}
      {!technologies &&
        !categories &&
        !permissions.capabilities.includes("technology.create") &&
        !permissions.capabilities.includes("category.create") && (
          <StatePanel kind="empty" title={t("registry")} description={t("notPermitted")} />
        )}
      {technologies && (
        <section aria-label={t("registry")}>
          {technologies.items.length === 0 ? (
            <StatePanel kind="empty" title={t("registry")} description={t("registryEmpty")} />
          ) : (
            <ul className="divide-border divide-y">
              {technologies.items.map((technology) => (
                <li key={technology.technology_id} className="space-y-2 py-4">
                  <h2 className="text-lg font-medium">
                    <Link
                      href={`/corporate/technologies/${technology.technology_id}`}
                      className="inline-flex min-h-11 items-center underline underline-offset-4"
                    >
                      {technology.name}
                    </Link>
                  </h2>
                  <p className="text-muted-foreground text-sm">
                    {t(`values.${technology.lifecycle}`)}
                  </p>
                  {technology.description && (
                    <p className="max-w-prose text-sm">{technology.description}</p>
                  )}
                  {technology.aliases.length > 0 && (
                    <p className="text-sm">
                      {t("aliases")}: {technology.aliases.join(", ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
