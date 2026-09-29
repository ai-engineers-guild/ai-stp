import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";
import { CatalogResults } from "@/components/organisms/catalog-results";
import { ApiError } from "@/lib/api/errors";
import { listCatalogReactions } from "@/lib/api/reactions";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { loadPublisherProfiles } from "@/lib/catalog-load";
import { catalogResultsLabels } from "@/lib/catalog-results-labels";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type PageProps = { params: Promise<{ locale: string }> };

export default async function MyLikesPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/likes`);
  const [t, tc, tCatalog] = await Promise.all([
    getTranslations("myLikes"),
    getTranslations("common"),
    getTranslations("catalog"),
  ]);
  let reactions;
  try {
    reactions = await listCatalogReactions(await sessionCookieValue());
  } catch (error) {
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }
  const items = reactions.items.map((item) => item.summary);
  const authors = await loadPublisherProfiles(items.map((item) => item.publisher_id));

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header className="border-border grid gap-5 border-b pb-7 sm:grid-cols-[1fr_auto] sm:items-end">
        <div className="space-y-2">
          <div className="text-primary flex items-center gap-2 text-sm font-medium">
            <Icon name="heart" size="sm" fill="currentColor" />
            {t("results")}
          </div>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("title")}</h1>
          <p className="text-muted-foreground max-w-2xl text-sm leading-relaxed">{t("subtitle")}</p>
        </div>
        <p className="text-muted-foreground font-mono text-sm tabular-nums">{items.length}</p>
      </header>

      {items.length === 0 ? (
        <div className="space-y-5">
          <StatePanel kind="empty" title={t("empty")} description={t("emptyHint")} />
          <Button asChild>
            <Link href="/catalog?include_experimental=1">
              <Icon name="search" size="sm" /> {t("browse")}
            </Link>
          </Button>
        </div>
      ) : (
        <CatalogResults
          kind="mixed"
          items={items}
          experimental={[]}
          nextCursor={null}
          totalItems={items.length}
          showExperimental={false}
          basePath="/likes"
          query={{}}
          locale={locale}
          authors={authors}
          labels={catalogResultsLabels(tCatalog, tc, {
            resultsHeading: t("results"),
            emptyAuthoritative: t("empty"),
            emptyExperimental: t("empty"),
            emptyAll: t("empty"),
            publishedAt: tCatalog("publishedAt"),
          })}
          likedIds={items.map((item) => item.stable_id)}
        />
      )}
    </div>
  );
}
