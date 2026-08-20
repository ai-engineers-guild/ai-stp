import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ContactForm } from "@/components/organisms/contact-form";
import { CONTACT_EMAIL_PLACEHOLDER } from "@/lib/site";
import { UI } from "@/lib/ui-selectors";

type PageProps = { params: Promise<{ locale: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "contact" });
  return {
    title: t("title"),
    description: t("subtitle"),
    alternates: {
      canonical: `/${locale}/contact`,
      languages: { ru: "/ru/contact", en: "/en/contact" },
    },
  };
}

export default async function ContactPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("contact");
  const recipient = process.env["NEXT_PUBLIC_CONTACT_EMAIL"] ?? CONTACT_EMAIL_PLACEHOLDER;

  return (
    <section
      data-ui={UI.contact.page}
      className="grid gap-12 py-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-20 lg:py-12"
    >
      <header className="space-y-8 lg:sticky lg:top-28 lg:self-start">
        <div className="space-y-5">
          <h1 className="max-w-xl text-5xl font-medium tracking-[-0.04em] text-balance sm:text-6xl">
            {t("title")}
          </h1>
          <p className="text-muted-foreground max-w-lg text-lg leading-relaxed sm:text-xl">
            {t("subtitle")}
          </p>
        </div>
        <div className="border-y py-5">
          <p className="text-muted-foreground mb-2 font-mono text-xs uppercase">{t("direct")}</p>
          <a
            href={`mailto:${recipient}`}
            className="focus-visible:ring-ring decoration-primary text-lg break-all underline underline-offset-4 focus-visible:ring-2 focus-visible:outline-none"
          >
            {recipient}
          </a>
        </div>
        <div className="space-y-2">
          <h2 className="font-mono text-xs font-medium uppercase">{t("responseTitle")}</h2>
          <p className="text-muted-foreground max-w-md text-sm leading-relaxed">
            {t("responseHint")}
          </p>
        </div>
      </header>
      <div className="bg-card rounded-lg p-5 sm:p-8">
        <div className="mb-8 space-y-2 border-b pb-6">
          <h2 className="text-2xl font-medium tracking-tight">{t("formTitle")}</h2>
          <p className="text-muted-foreground max-w-xl text-sm leading-relaxed">{t("formHint")}</p>
        </div>
        <ContactForm
          recipient={recipient}
          placeholderRecipient={recipient === CONTACT_EMAIL_PLACEHOLDER}
        />
      </div>
    </section>
  );
}
