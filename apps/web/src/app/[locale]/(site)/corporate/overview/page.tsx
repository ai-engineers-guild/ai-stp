import { CorporateOverview } from "../page";

export default async function CorporateOverviewAlias({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return CorporateOverview({ params, returnTo: `/${locale}/corporate/overview` });
}
