import { permanentRedirect } from "next/navigation";

export default async function LegacyUsagePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  permanentRedirect(`/${locale}/corporate/reports/usage`);
}
