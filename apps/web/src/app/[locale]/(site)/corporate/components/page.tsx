import { getTranslations, setRequestLocale } from "next-intl/server";

import { StatePanel } from "@/components/molecules/state-panel";
import { CorporateDirectory } from "@/components/organisms/corporate-directory";
import { readCorporateContext, readCorporateDirectoryPages } from "@/lib/api/corporate";
import { ApiError } from "@/lib/api/errors";
import { listCatalogAuthors, searchComponents } from "@/lib/api/catalog";
import type { ComponentType } from "@/lib/api/generated/types.gen";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import type {
  CorporateCatalogFacetConfig,
  DirectoryItem,
} from "@/components/organisms/corporate-directory-types";

type CatalogSearchParams = Record<string, string | string[] | undefined>;

function readCatalogFilters(raw: CatalogSearchParams) {
  const query =
    typeof raw.q === "string" ? raw.q : typeof raw.query === "string" ? raw.query : undefined;
  const values = (key: string) => {
    const value = raw[key];
    return (Array.isArray(value) ? value : value ? [value] : [])
      .flatMap((item) => item.split(","))
      .map((item) => item.trim())
      .filter(Boolean);
  };
  const assignment: "direct" | "effective" | undefined =
    raw.assignment === "direct" || raw.assignment === "effective" ? raw.assignment : undefined;
  const corporateVerified =
    raw.corporate_verified === "true"
      ? true
      : raw.corporate_verified === "false"
        ? false
        : undefined;
  return { query, values, assignment, corporateVerified };
}

export default async function CorporateComponentsPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/corporate/components`);
  const t = await getTranslations("hub");
  const common = await getTranslations("common");
  const catalog = await getTranslations("catalog");
  const token = (await sessionCookieValue()) ?? "";
  const context = await readCorporateContext(token);
  if (!context) return <StatePanel kind="empty" title={t("components")} description={t("empty")} />;
  const { query, values, assignment, corporateVerified } = readCatalogFilters(await searchParams);
  const organizationId = context.organization.organization_id;
  const [memberDirectory, technologyDirectory] = await Promise.allSettled([
    readCorporateDirectoryPages(token, organizationId, {
      resource: "members",
      include_archived: false,
    }),
    readCorporateDirectoryPages(token, organizationId, {
      resource: "technologies",
      include_archived: false,
    }),
  ]);
  const refs = (result: PromiseSettledResult<{ items: readonly DirectoryItem[] }>) =>
    result.status === "fulfilled" ? result.value.items : [];
  const optionList = (items: readonly { id: string; name: string }[]) =>
    [
      ...new Map(items.map((item) => [item.id, { value: item.id, label: item.name }])).values(),
    ].sort((left, right) => left.label.localeCompare(right.label));
  const teamOptions = optionList(
    context.teams.map((team) => ({ id: team.team_id, name: team.name })),
  );
  const projectOptions = optionList(
    context.projects.map((project) => ({ id: project.project_id, name: project.name })),
  );
  const technologyOptions = optionList(refs(technologyDirectory));
  const ownerOptions = optionList([
    { id: organizationId, name: context.organization.display_name },
    ...context.teams.map((team) => ({ id: team.team_id, name: team.name })),
    ...context.projects.map((project) => ({ id: project.project_id, name: project.name })),
    ...refs(technologyDirectory),
    ...refs(memberDirectory),
  ]);
  const maintainerOptions = optionList([
    ...context.teams.map((team) => ({ id: team.team_id, name: team.name })),
    ...refs(memberDirectory),
  ]);
  const catalogFacets: CorporateCatalogFacetConfig[] = [
    { key: "team_ids", label: t("teams"), options: teamOptions },
    { key: "project_ids", label: t("projects"), options: projectOptions },
    { key: "technology_ids", label: t("technologies"), options: technologyOptions },
    { key: "owner_ids", label: t("catalogOwner"), options: ownerOptions },
    { key: "maintainer_ids", label: t("catalogMaintainer"), options: maintainerOptions },
    {
      key: "assignment",
      label: t("catalogAssignment"),
      multiple: false,
      options: [
        { value: "direct", label: t("directAssignment") },
        { value: "effective", label: t("effectiveAssignment") },
      ],
    },
    {
      key: "corporate_verified",
      label: t("corporateVerification"),
      multiple: false,
      options: [
        { value: "true", label: t("verified") },
        { value: "false", label: t("notVerified") },
      ],
    },
  ];
  let rows: Array<{
    id: string;
    name: string;
    description?: string;
    component_type?: ComponentType;
    author_name?: string;
    owner_name?: string | null;
    tags?: readonly string[];
    version?: string;
  }> = [];
  try {
    const [result, authors] = await Promise.all([
      searchComponents({
        ...(query ? { q: query } : {}),
        sessionToken: token,
        organization_id: organizationId,
        team_ids: values("team_ids"),
        project_ids: values("project_ids"),
        technology_ids: values("technology_ids"),
        owner_ids: values("owner_ids"),
        maintainer_ids: values("maintainer_ids"),
        ...(assignment ? { assignment } : {}),
        ...(corporateVerified !== undefined ? { corporate_verified: corporateVerified } : {}),
        page_size: 100,
        include_experimental: true,
      }),
      listCatalogAuthors().catch(() => ({ items: [] })),
    ]);
    const authorNames = new Map(
      authors.items.map((author) => [
        author.account_id,
        author.display_name || [author.first_name, author.last_name].filter(Boolean).join(" "),
      ]),
    );
    rows = [...result.items, ...result.experimental].map((item) => ({
      id: item.stable_id,
      name: item.latest_name,
      description: item.latest_description,
      component_type: item.latest_component_type,
      author_name: authorNames.get(item.publisher_id) || item.owner_handle || catalog("author"),
      owner_name: authorNames.get(item.owner_account_id) || item.owner_handle || null,
      tags: item.latest_tags,
      version: item.latest_version,
    }));
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return (
      <StatePanel kind="error" title={t("components")} description={common("apiUnavailable")} />
    );
  }
  return (
    <CorporateDirectory
      resource="components"
      items={rows}
      organizationId={context.organization.organization_id}
      authorizationRevision={context.organization.authorization_revision}
      csrfToken={(await readCsrfToken()) ?? ""}
      canCreate={false}
      roles={[]}
      initialQuery={query ?? ""}
      catalogFacets={catalogFacets}
      catalogFacetValues={{
        team_ids: values("team_ids"),
        project_ids: values("project_ids"),
        technology_ids: values("technology_ids"),
        owner_ids: values("owner_ids"),
        maintainer_ids: values("maintainer_ids"),
        assignment: assignment ? [assignment] : [],
        corporate_verified: corporateVerified === undefined ? [] : [String(corporateVerified)],
      }}
    />
  );
}
