import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";

import { MachineDocumentView } from "@/components/layouts/machine-document";
import { resolveMachineDocument } from "@/lib/projection/registry";

type PageProps = {
  params: Promise<{ locale: string; path?: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/**
 * The machine projection of the whole site. A real route segment rather than a
 * rewrite of the human tree, so both projections keep their own layout and the
 * client router never mixes them (ADR-0056).
 */
export default async function MachineProjectionPage({ params, searchParams }: PageProps) {
  const { locale, path } = await params;
  setRequestLocale(locale);
  const segments = path ?? [];
  const document = await resolveMachineDocument({
    locale,
    segments,
    searchParams: await searchParams,
  });

  if (!document) {
    notFound();
  }

  return <MachineDocumentView document={document} locale={locale} />;
}
