import { permanentRedirect } from "next/navigation";

export default async function LegacyInstallationsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  permanentRedirect(`/${locale}/corporate/reports/heartbeat`);
}
