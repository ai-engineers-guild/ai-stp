import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import {
  ScopedObjectFilters,
  type ObjectFilterKind,
} from "@/components/molecules/scoped-object-filters";
import { StatePanel } from "@/components/molecules/state-panel";
import { OwnerObjectActions } from "@/components/organisms/owner-object-actions";
import { ApiError } from "@/lib/api/errors";
import { listOwnerObjects } from "@/lib/api/owner";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { readCsrfToken } from "@/lib/auth/session";
import { ownerComponentNextStep, ownerSetupNextStep } from "@/lib/cli-copy";
import { Link } from "@/lib/i18n/navigation";

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
  const session = await requireSession(locale, `/${locale}/objects`);
  const csrfToken = (await readCsrfToken()) ?? "";
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
                <OwnerObjectActions
                  csrfToken={csrfToken}
                  deviceId={session.deviceId}
                  kind={item.object_kind}
                  stableId={item.stable_id}
                  name={item.name}
                  version={item.latest_version}
                  visibility={item.visibility}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
