import { getTranslations, setRequestLocale } from "next-intl/server";

import { Button } from "@/components/atoms/button";
import { InstallBlock } from "@/components/organisms/install-block";
import { readSession } from "@/lib/auth/session";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";

type PageProps = {
  params: Promise<{ locale: string }>;
};

export default async function LandingPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("landing");
  const signedIn = (await readSession()) !== null;

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
            {!signedIn ? (
              <Button asChild variant="outline" className="min-h-11 w-full sm:w-auto">
                <Link href="/login">{t("signIn")}</Link>
              </Button>
            ) : null}
          </div>
        </div>
        <div
          data-ui={UI.landing.preview}
          className="border-border bg-card relative aspect-video min-w-0 overflow-hidden rounded-xl border lg:aspect-auto lg:h-68"
          aria-label={t("previewLabel")}
        >
          <video
            className="h-full w-full object-cover motion-reduce:hidden"
            autoPlay
            muted
            loop
            playsInline
            preload="metadata"
          >
            <source src="/brand/hero-preview.webm" type="video/webm" />
          </video>
          <div className="from-background/10 via-background/20 to-background/80 pointer-events-none absolute inset-0 bg-gradient-to-br" />
          <div className="absolute right-4 bottom-4 left-4 font-mono text-xs break-words text-white">
            {t("previewCaption")}
          </div>
        </div>
      </section>
      <InstallBlock />
    </div>
  );
}
