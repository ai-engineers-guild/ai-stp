import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import type { Metadata } from "next";

import "../globals.css";

import { AppProviders } from "@/components/providers/app-providers";
import { locales, type AppLocale } from "@/lib/i18n/routing";
import {
  pairedPath,
  pathWithoutLocale,
  readCanonicalPathname,
  readProjection,
} from "@/lib/projection/mode";
import { publicOrigin, SITE_NAME } from "@/lib/site";

type LocaleLayoutProps = {
  children: ReactNode;
  params: Promise<{ locale: string }>;
};

// Projection and canonical URL are request-header driven (SPEC-036 / ADR-0076).
// headers() in this layout is the minimal dynamic boundary for data-mode and
// canonical metadata. Do not set force-dynamic here: public pages own fetch
// cache via the public GET helper (SPEC-048 / ADR-0095).

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta" });
  // One canonical per document: the human URL of the current page. A machine
  // URL never claims its own canonical (REQ-3616).
  const canonicalPath = pairedPath(
    pathWithoutLocale((await readCanonicalPathname()) ?? `/${locale}`, locale),
    "human",
    locale,
  );
  return {
    metadataBase: publicOrigin(),
    title: { default: t("siteName"), template: `%s · ${SITE_NAME}` },
    description: t("defaultDescription"),
    applicationName: SITE_NAME,
    authors: [{ name: "NDDev" }],
    creator: "NDDev",
    manifest: "/manifest.webmanifest",
    alternates: {
      canonical: canonicalPath,
      languages: { ru: "/ru", en: "/en", "x-default": "/ru" },
    },
    openGraph: {
      type: "website",
      siteName: SITE_NAME,
      locale: locale === "ru" ? "ru_RU" : "en_US",
      title: t("siteName"),
      description: t("defaultDescription"),
      images: [{ url: "/brand/icon-512.png", width: 512, height: 512, alt: SITE_NAME }],
    },
    twitter: {
      card: "summary",
      title: t("siteName"),
      description: t("defaultDescription"),
      images: ["/brand/icon-512.png"],
    },
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        "max-image-preview": "large",
        "max-snippet": -1,
        "max-video-preview": -1,
      },
    },
  };
}

function isLocale(value: string): value is AppLocale {
  return (locales as readonly string[]).includes(value);
}

export default async function LocaleLayout({ children, params }: LocaleLayoutProps) {
  const { locale } = await params;
  if (!isLocale(locale)) {
    notFound();
  }
  setRequestLocale(locale);
  const messages = await getMessages();
  const meta = await getTranslations({ locale, namespace: "meta" });
  const projection = await readProjection();
  const canonical = (await readCanonicalPathname()) ?? `/${locale}`;
  const pagePath = pathWithoutLocale(canonical, locale);
  const humanHref = pairedPath(pagePath, "human", locale);
  const machineHref = pairedPath(pagePath, "machine", locale);
  const alternateHref = projection === "human" ? machineHref : humanHref;

  return (
    <html lang={locale} data-mode={projection} suppressHydrationWarning>
      <head>
        <meta name="description" content={meta("defaultDescription")} />
        <link rel="alternate" href={alternateHref} />
      </head>
      <body>
        <NextIntlClientProvider messages={messages}>
          <AppProviders>{children}</AppProviders>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
