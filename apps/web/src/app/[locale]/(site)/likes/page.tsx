import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";
import { CatalogResults } from "@/components/organisms/catalog-results";
import { listCatalogReactions } from "@/lib/api/reactions";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";
import { loadPublisherProfiles } from "@/lib/catalog-load";
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
  const reactions = await listCatalogReactions(await sessionCookieValue());
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
          labels={{
            authoritative: tCatalog("authoritative"),
            experimental: tCatalog("experimental"),
            experimentalNote: tCatalog("experimentalNote"),
            emptyAuthoritative: t("empty"),
            emptyExperimental: t("empty"),
            emptyAll: t("empty"),
            resultsHeading: t("results"),
            nextPage: tCatalog("nextPage"),
            version: tCatalog("version"),
            harness: tCatalog("harness"),
            type: tCatalog("type"),
            tags: tCatalog("tags"),
            purpose: tCatalog("purpose"),
            targetRole: tCatalog("targetRole"),
            authorVerified: tCatalog("authorVerified"),
            githubStars: tCatalog("githubStars"),
            componentVerified: tCatalog("componentVerified"),
            yes: tc("yes"),
            no: tc("no"),
            publisher: tCatalog("publisher"),
            publishedAt: tCatalog("publishedAt"),
            likes: tCatalog("likes"),
            detailViews: tCatalog("detailViews"),
            artifactDownloads: tCatalog("artifactDownloads"),
            componentKind: tCatalog("componentKind"),
            setupKind: tCatalog("setupKind"),
            moreActions: tCatalog("moreActions"),
            copyCli: tCatalog("copyCli"),
            copyId: tCatalog("copyId"),
            copyUrl: tCatalog("copyUrl"),
            copied: tCatalog("copied"),
            report: tCatalog("report"),
            reportSetup: tCatalog("reportSetup"),
            whyFailed: tCatalog("whyFailed"),
            whyWarning: tCatalog("whyWarning"),
            requirements: tCatalog("requirements"),
            credentialsRequired: tCatalog("credentialsRequired"),
            safetyChecks: tCatalog("safetyChecks"),
            safetyNoScan: tCatalog("safetyNoScan"),
          }}
        />
      )}
    </div>
  );
}
