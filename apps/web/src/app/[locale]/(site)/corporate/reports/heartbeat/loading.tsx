import { getTranslations } from "next-intl/server";
import { Skeleton } from "@/components/atoms/skeleton";

export default async function HeartbeatReportLoading() {
  const t = await getTranslations("corporateReports");
  return (
    <main
      className="mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-6"
      aria-busy="true"
      aria-label={t("loading")}
    >
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-9 w-80" />
      <Skeleton className="h-24 w-full" />
      <div className="border-border space-y-3 rounded-lg border p-4">
        {[0, 1, 2, 3, 4].map((row) => (
          <Skeleton key={row} className="h-9 w-full" />
        ))}
      </div>
    </main>
  );
}
