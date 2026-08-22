import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { InstallBlock } from "@/components/organisms/install-block";
import { SignedOutOnly } from "@/components/molecules/signed-out-only";
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
    <div data-ui={UI.landing.page} className="flex min-w-0 flex-col gap-5">
      <section className="grid min-w-0 items-center gap-8 lg:grid-cols-[1fr_1.05fr] lg:gap-12">
        <div className="min-w-0 space-y-4">
          <h1 className="text-[1.75rem] leading-tight font-medium tracking-tight sm:text-4xl lg:text-5xl">
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
              <Button asChild variant="outline" className="min-h-11 w-full sm:w-auto">
                <Link href="/login">{t("signIn")}</Link>
              </Button>
            </SignedOutOnly>
          </div>
        </div>
        <div
          data-ui={UI.landing.preview}
          className="border-border bg-card relative aspect-video min-w-0 overflow-hidden rounded-xl border lg:aspect-auto lg:h-68"
        >
          <video
            className="h-full w-full object-cover motion-reduce:hidden"
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
            aria-label={t("previewLabel")}
          >
            <source src="/brand/hero-preview.webm" type="video/webm" />
          </video>
        </div>
      </section>
      <InstallBlock />
    </div>
  );
}
