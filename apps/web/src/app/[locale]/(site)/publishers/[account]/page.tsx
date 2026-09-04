import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Badge } from "@/components/atoms/badge";
import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import { VerifiedAvatar } from "@/components/molecules/verified-avatar";
import { Button } from "@/components/atoms/button";
import { ObjectCard } from "@/components/organisms/object-card";
import { StatePanel } from "@/components/molecules/state-panel";
import { searchComponents, searchSetups } from "@/lib/api/catalog";
import { readPublisherProfile } from "@/lib/api/public-profile";
import { asAccountId } from "@/lib/brands";
import { buildDeepLink, normalizeTarget } from "@/lib/deep-links";
import { publicOrigin } from "@/lib/site";
import { readSession } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";
import { renderMarkdownOnServer } from "@/lib/markdown/render";

function linkHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function ProfileLinks({ links }: { links: ReadonlyArray<{ label: string; url: string }> }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {links.map((link) => (
        <li key={`${link.label}-${link.url}`}>
          <a
            href={link.url}
            className="border-border hover:bg-muted focus-visible:ring-ring inline-flex min-w-0 items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
            rel="noopener noreferrer"
            target="_blank"
          >
            <span className="font-medium">{link.label}</span>
            <span className="text-muted-foreground max-w-44 truncate font-mono text-xs">
              {linkHost(link.url)}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

type PageProps = {
  params: Promise<{ locale: string; account: string }>;
};

/**
 * Public publisher profile (SPEC-028 / REQ-2210). Published allowlist only.
 */
// Page owns both human layout and machine presenter branch from the same reads.

// The server page intentionally keeps profile and published-object states together.
// eslint-disable-next-line max-lines-per-function
export default async function PublisherPage({ params }: PageProps) {
  const { locale, account } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("publisher");
  const tc = await getTranslations("common");
  const tCatalog = await getTranslations("catalog");
  const tAccount = await getTranslations("account");
  const tCli = await getTranslations("cli");
  const session = await readSession();

  const accountId = (() => {
    try {
      return asAccountId(account);
    } catch {
      notFound();
    }
  })();

  let profile;
  try {
    profile = await readPublisherProfile(accountId);
  } catch {
    notFound();
  }

  const [components, setups] = await Promise.all([
    searchComponents({ authors: [accountId], page_size: 100, include_experimental: true }),
    searchSetups({ authors: [accountId], page_size: 100, include_experimental: true }),
  ]);
  const objects = {
    components: [...components.items, ...components.experimental],
    setups: [...setups.items, ...setups.experimental],
  };
  const isEmpty =
    Boolean(profile.empty) ||
    (profile.display_name === null &&
      profile.bio === null &&
      profile.links.length === 0 &&
      !profile.avatar_url);
  const isOwner = session?.accountId === accountId;
  let publisherLink: string | null = null;
  try {
    publisherLink = buildDeepLink(
      publicOrigin().origin,
      normalizeTarget({
        kind: "publisher",
        stable_id: accountId,
        locale: locale === "en" ? "en" : "ru",
      }),
    ).cli_command;
  } catch {
    publisherLink = null;
  }
  const authorVerified = profile.author_verified;

  const cardLabels = {
    version: tCatalog("version"),
    harness: tCatalog("harness"),
    type: tCatalog("type"),
    tags: tCatalog("tags"),
    authorVerified: tCatalog("authorVerified"),
    authorVerifiedDescription: tCatalog("authorVerifiedDescription"),
    componentVerified: tCatalog("componentVerified"),
    yes: tc("yes"),
    no: tc("no"),
    publisher: tCatalog("publisher"),
    likes: tCatalog("likes"),
    setupKind: tCatalog("setupKind"),
    componentKind: tCatalog("componentKind"),
    moreActions: tCatalog("moreActions"),
    copyCli: tCatalog("copyCli"),
    copyId: tCatalog("copyId"),
    copied: tCatalog("copied"),
    report: tCatalog("report"),
    safetyCheckExplanation: tCatalog("safetyCheckExplanation"),
    likeMenu: tCatalog("likeMenu"),
    unlikeMenu: tCatalog("unlikeMenu"),
  };

  return (
    <article className="space-y-6">
      <p className="text-sm">
        <Link href="/catalog?include_experimental=1" className="underline">
          {tCatalog("backToCatalog")}
        </Link>
      </p>
      <section className="flex flex-wrap items-start gap-6 sm:pl-4">
        <VerifiedAvatar
          src={profile.avatar_url}
          verified={authorVerified}
          verifiedLabel={tCatalog("authorVerified")}
          size="lg"
          fallback={(profile.display_name ?? profile.account_id).slice(0, 2).toUpperCase()}
        />
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-medium tracking-tight">
              {profile.display_name ?? t("title")}
            </h1>
            {authorVerified ? <Badge variant="success">{tCatalog("authorVerified")}</Badge> : null}
            {isOwner ? (
              <Button asChild variant="outline" size="sm">
                <Link href="/account/profile">{tAccount("profileEdit")}</Link>
              </Button>
            ) : null}
            <Button asChild variant="outline" size="sm">
              <Link
                href={`/reports?topic=author_complaint&author=${encodeURIComponent(profile.account_id)}`}
              >
                {tCatalog("reportAuthorType")}
              </Link>
            </Button>
          </div>
          <p className="font-mono text-sm break-all">{profile.account_id}</p>
          {publisherLink ? (
            <CliCopyBlock
              command={publisherLink}
              title={tCli("useTitle")}
              copyLabel={tCli("copy")}
              copiedLabel={tCli("copied")}
              errorLabel={tCli("copyError")}
              docsLabel={tCli("docs")}
            />
          ) : null}
          {isEmpty ? (
            <p className="text-muted-foreground">{t("emptyProfile")}</p>
          ) : (
            <>
              {profile.links.length > 0 ? <ProfileLinks links={profile.links} /> : null}
              {profile.bio ? (
                <div
                  className="prose-sm text-muted-foreground max-w-prose text-sm leading-relaxed [&_a]:underline [&_code]:font-mono"
                  dangerouslySetInnerHTML={{
                    __html: renderMarkdownOnServer(profile.bio).html,
                  }}
                />
              ) : null}
            </>
          )}
        </div>
      </section>

      <section className="space-y-4" aria-labelledby="published-objects-heading">
        <h2 id="published-objects-heading" className="text-xl font-medium tracking-tight">
          {t("publishedObjects")}
        </h2>
        {objects.components.length === 0 && objects.setups.length === 0 ? (
          <StatePanel kind="empty" title={t("noObjects")} />
        ) : (
          <>
            {objects.components.length > 0 ? (
              <div className="space-y-3">
                <h3 className="text-lg font-medium">{t("components")}</h3>
                <ul className="grid min-w-0 gap-4 md:grid-cols-2">
                  {objects.components.map((item) => (
                    <li key={item.stable_id} className="min-w-0">
                      <ObjectCard
                        kind="component"
                        item={item}
                        href={`/catalog/components/${item.stable_id}`}
                        labels={cardLabels}
                        view="cards"
                        author={{
                          displayName: profile.display_name,
                          avatarUrl: profile.avatar_url,
                        }}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {objects.setups.length > 0 ? (
              <div className="space-y-3">
                <h3 className="text-lg font-medium">{t("setups")}</h3>
                <ul className="grid min-w-0 gap-4 md:grid-cols-2">
                  {objects.setups.map((item) => (
                    <li key={item.stable_id} className="min-w-0">
                      <ObjectCard
                        kind="setup"
                        item={item}
                        href={`/catalog/setups/${item.stable_id}`}
                        labels={cardLabels}
                        view="cards"
                        author={{
                          displayName: profile.display_name,
                          avatarUrl: profile.avatar_url,
                        }}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}
      </section>

      {!isEmpty ? (
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{t("publicProfileBadge")}</Badge>
        </div>
      ) : null}
    </article>
  );
}
