import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { listOwnerObjects } from "@/lib/api/owner";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { ownerComponentNextStep, ownerSetupNextStep } from "@/lib/cli-copy";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function OwnerObjectsPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/objects`);
  const t = await getTranslations("objects");
  const tc = await getTranslations("common");
  const tCli = await getTranslations("cli");
  const token = await sessionCookieValue();

  let list;
  try {
    list = await listOwnerObjects(token ?? "");
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
        <ul className="divide-border border-border divide-y rounded-lg border">
          {list.items.map((item) => (
            <li
              key={`${item.object_kind}:${item.stable_id}`}
              className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 space-y-1">
                <p className="text-muted-foreground font-mono text-xs tracking-wide uppercase">
                  {item.object_kind}
                </p>
                <Link
                  href={`/objects/${item.object_kind}/${item.stable_id}`}
                  className="block truncate font-medium underline-offset-4 hover:underline"
                >
                  {item.name}
                </Link>
                <p className="text-muted-foreground font-mono text-xs">{item.stable_id}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
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
                <Button asChild variant="outline" size="sm">
                  <Link
                    href={`/catalog/${item.object_kind === "component" ? "components" : "setups"}/${item.stable_id}`}
                  >
                    <Icon name="eye" size="sm" /> {t("viewPublic")}
                  </Link>
                </Button>
                <Button asChild size="sm">
                  <Link href={`/objects/${item.object_kind}/${item.stable_id}`}>
                    <Icon name="edit" size="sm" /> {t("manageObject")}
                  </Link>
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
