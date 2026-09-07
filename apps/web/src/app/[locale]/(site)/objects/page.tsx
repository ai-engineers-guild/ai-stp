import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import {
  ScopedObjectFilters,
  type ObjectFilterKind,
} from "@/components/molecules/scoped-object-filters";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { listOwnerObjects } from "@/lib/api/owner";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { ownerComponentNextStep, ownerSetupNextStep } from "@/lib/cli-copy";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type PageProps = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ kind?: string }>;
};

function selectedKind(value: string | undefined): ObjectFilterKind {
  return value === "component" || value === "setup" ? value : "all";
}

export default async function OwnerObjectsPage({ params, searchParams }: PageProps) {
  const { locale } = await params;
  const sp = await searchParams;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/objects`);
  const t = await getTranslations("objects");
  const tc = await getTranslations("common");
  const tCli = await getTranslations("cli");
  const tCatalog = await getTranslations("catalog");
  const token = await sessionCookieValue();
  const kind = selectedKind(sp.kind);

  let list;
  try {
    list = await listOwnerObjects(token ?? "", {
      ...(kind !== "all" ? { object_kind: kind } : {}),
    });
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground max-w-2xl text-sm">{t("subtitle")}</p>
      </div>

      {list.items.length === 0 ? (
        <div className="space-y-4">
          <StatePanel
            kind="empty"
            title={tCli("ownerEmptyTitle")}
            description={tCli("ownerEmptyBody")}
          />
          <CliCopyBlock
            command={ownerComponentNextStep()}
            title={tCli("syncCommandHint")}
            copyLabel={tCli("copy")}
            copiedLabel={tCli("copied")}
            errorLabel={tCli("copyError")}
            docsLabel={tCli("docs")}
          />
          <CliCopyBlock
            command={ownerSetupNextStep()}
            title={tCli("setupNextStepHint")}
            copyLabel={tCli("copy")}
            copiedLabel={tCli("copied")}
            errorLabel={tCli("copyError")}
            docsLabel={tCli("docs")}
          />
        </div>
      ) : (
        <div className="space-y-4">
          <ScopedObjectFilters
            kind={kind}
            resetHref="/objects"
            labels={{
              title: tCatalog("filtersButton"),
              description: tCatalog("scopedFilterDescription"),
              activeCount: tCatalog("activeCount"),
              activeFilters: tCatalog("activeFilters"),
              noActiveFilters: tCatalog("noActiveFilters"),
              clear: tCatalog("resetAll"),
              apply: tCatalog("applyFilters"),
              objectType: tCatalog("objectType"),
              allTypes: tCatalog("allTypes"),
              components: tCatalog("components"),
              setups: tCatalog("setups"),
              verifiedOnly: tCatalog("verifiedOnly"),
            }}
          />
          <ul className="divide-border border-border divide-y rounded-lg border">
            {list.items.map((item) => (
              <li
                key={`${item.object_kind}:${item.stable_id}`}
                className="relative grid min-w-0 gap-4 px-4 py-4 pr-16 md:grid-cols-[minmax(15rem,1fr)_auto] md:items-center"
              >
                <div className="min-w-0 space-y-1">
                  <p className="text-muted-foreground font-mono text-xs tracking-wide uppercase">
                    {item.object_kind}
                  </p>
                  <Link
                    href={`/objects/${item.object_kind}/${item.stable_id}`}
                    className="block max-w-prose font-medium break-words underline-offset-4 hover:underline"
                  >
                    {item.name}
                  </Link>
                  <p className="text-muted-foreground font-mono text-xs">{item.stable_id}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2 sm:justify-self-start">
                  {item.latest_version ? (
                    <span className="font-mono text-xs">{item.latest_version}</span>
                  ) : null}
                  <Badge variant="outline" className="font-mono text-xs">
                    {item.lifecycle_state}
                  </Badge>
                  <Badge variant="secondary" className="font-mono text-xs">
                    {item.visibility}
                  </Badge>
                  {item.author_verified ? (
                    <Badge variant="outline">{t("authorVerified")}</Badge>
                  ) : null}
                  {item.component_verified ? <Badge>{t("componentVerified")}</Badge> : null}
                </div>
                <details className="absolute top-4 right-4">
                  <summary
                    className="border-border hover:bg-muted flex size-10 cursor-pointer list-none items-center justify-center rounded-md border"
                    aria-label={t("manageObject")}
                  >
                    <Icon name="more" size="sm" />
                  </summary>
                  <div className="border-border bg-popover absolute top-11 right-0 z-20 grid min-w-56 rounded-lg border p-1 shadow-md">
                    <Link
                      className="hover:bg-muted rounded-md px-3 py-2 text-sm"
                      href={`/catalog/${item.object_kind === "component" ? "components" : "setups"}/${item.stable_id}`}
                    >
                      {t("viewPublic")}
                    </Link>
                    <Link
                      className="hover:bg-muted rounded-md px-3 py-2 text-sm"
                      href={`/objects/${item.object_kind}/${item.stable_id}/edit`}
                    >
                      {t("editPresentation")}
                    </Link>
                    <Link
                      className="hover:bg-muted rounded-md px-3 py-2 text-sm"
                      href={`/objects/${item.object_kind}/${item.stable_id}`}
                    >
                      {t("manageAccess")}
                    </Link>
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
