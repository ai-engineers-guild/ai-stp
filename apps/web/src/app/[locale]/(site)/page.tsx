import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { LandingHeroPreview } from "@/components/molecules/landing-hero-preview";
import { SignedOutOnly } from "@/components/molecules/signed-out-only";
import { InstallBlock } from "@/components/organisms/install-block";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("landing");
  const description = t("seoDescription");
  return {
    title: t("title"),
    description,
    keywords: [
      "AI setup",
      "MCP",
      "skills",
      "hooks",
      "subagents",
      "Claude Code",
      "Codex",
      "skills.sh",
    ],
    openGraph: { title: t("title"), description },
    twitter: { title: t("title"), description },
  };
}

export default async function LandingPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("landing");

  return (
    <div data-ui={UI.landing.page} className="min-w-0">
      <section className="landing-hero dark bg-background text-foreground relative left-1/2 isolate -my-6 flex min-h-[calc(100dvh-4rem)] w-screen -translate-x-1/2 items-center overflow-hidden px-4 py-16 sm:px-6">
        <div className="landing-hero__media" aria-hidden="true">
          <LandingHeroPreview />
        </div>
        <span className="sr-only">{t("previewLabel")}</span>
        <div className="landing-hero__veil" aria-hidden="true" />
        <div className="relative z-10 mx-auto grid w-full max-w-6xl min-w-0 items-center gap-10 lg:grid-cols-[minmax(0,1.05fr)_minmax(22rem,0.8fr)] lg:gap-16">
          <div className="min-w-0 space-y-5">
            <h1 className="max-w-3xl text-[2.25rem] leading-[1.08] font-medium tracking-[-0.035em] text-balance sm:text-5xl lg:text-6xl">
              {t("title")}
            </h1>
            <p className="text-muted-foreground max-w-2xl text-base leading-relaxed sm:text-lg">
              {t("subtitle")}
            </p>
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <Button asChild className="min-h-11 w-full sm:w-auto">
                <Link href="/catalog">{t("browseCatalog")}</Link>
              </Button>
              <SignedOutOnly>
                <Button
                  asChild
                  variant="outline"
                  className="min-h-11 w-full border-white/35 text-white hover:bg-white/10 sm:w-auto"
                >
                  <Link href="/login">{t("signIn")}</Link>
                </Button>
              </SignedOutOnly>
            </div>
          </div>
          <InstallBlock />
        </div>
      </section>
    </div>
  );
}
