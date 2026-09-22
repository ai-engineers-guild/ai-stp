import { setRequestLocale } from "next-intl/server";

import { UsageReportPanel } from "@/components/usage/usage-report-panel";

type Props = {
  params: Promise<{ locale: string }>;
};

export default async function CorporateUsagePage({ params }: Props) {
  const { locale } = await params;
  setRequestLocale(locale);
  // Session and organization resolve inside /api/corporate/usage; the panel
  // surfaces their failure as its error state rather than a second check here.
  // i18n catalog keys land at integration; the panel renders these defaults.
  return (
    <UsageReportPanel
      labels={{
        title: "Runtime usage",
        groupBy: "Group by",
        invocations: "Invocations",
        employees: "Employees",
        devices: "Devices",
        outcomes: "Succeeded / failed / cancelled",
        firstUsed: "First used",
        lastUsed: "Last used",
        installedTitle: "Assigned but never invoked",
        installedObject: "Object",
        installedState: "State",
        invoked: "Invoked",
        notInvoked: "Not invoked",
        loading: "Loading usage report",
        empty: "No usage events in this window",
        failed: "The usage report could not be loaded",
        retry: "Retry",
      }}
    />
  );
}
