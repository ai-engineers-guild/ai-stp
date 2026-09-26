import { getTranslations } from "next-intl/server";
import { Link } from "@/lib/i18n/navigation";
import { Sheet, SheetClose, SheetContent, SheetTitle } from "@/components/atoms/sheet";
import { StatePanel } from "@/components/molecules/state-panel";
import type {
  RuntimeUsageEventList,
  RuntimeUsageObjectRow,
  RuntimeUsageReport,
} from "@/lib/api/generated/types.gen";

type DrawerProps = {
  data: RuntimeUsageReport;
  detailError: number | null;
  eventList: RuntimeUsageEventList | null;
  detailPage: number;
  chartQuery: URLSearchParams;
  employeeId: string;
  selected: (key: string) => string;
  detailPageHref: (page: number) => string;
  focusedObject?: RuntimeUsageObjectRow | undefined;
};

type Translator = Awaited<ReturnType<typeof getTranslations<"corporateReports">>>;

function FocusedObjectDetails({
  focusedObject,
  employeeId,
  t,
}: {
  focusedObject: RuntimeUsageObjectRow;
  employeeId: string;
  t: Translator;
}) {
  return (
    <dl className="border-border mb-5 grid grid-cols-3 gap-2 rounded-lg border p-3 text-sm">
      <div>
        <dt className="text-muted-foreground">{t("detailAssignedTo")}</dt>
        <dd>{focusedObject.assigned_to}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">{t("detailInstalledFor")}</dt>
        <dd>{focusedObject.installed_for}</dd>
      </div>
      {employeeId && (
        <div>
          <dt className="text-muted-foreground">{t("detailInstallation")}</dt>
          <dd>{focusedObject.installation_state ?? t("unknown")}</dd>
        </div>
      )}
      <div>
        <dt className="text-muted-foreground">{t("detailUsedBy")}</dt>
        <dd>{focusedObject.used_by}</dd>
      </div>
      {employeeId && (
        <div>
          <dt className="text-muted-foreground">{t("detailLastCheck")}</dt>
          <dd>{focusedObject.last_checked_at ?? t("detailNoScan")}</dd>
        </div>
      )}
    </dl>
  );
}

function UsageEventCard({
  event,
  employeeName,
  inventory,
  t,
}: {
  event: RuntimeUsageEventList["events"][number];
  employeeName: string;
  inventory?: RuntimeUsageReport["inventory_employees"][number] | undefined;
  t: Translator;
}) {
  return (
    <article className="border-border rounded-lg border p-3 text-sm">
      <p className="font-medium">
        {event.component_stable_id}@{event.component_version}
      </p>
      <p className="text-muted-foreground">
        {event.invoked_at} · {event.outcome} · {event.source}
      </p>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
        <div>
          <dt className="text-muted-foreground">{t("filterEmployee")}</dt>
          <dd>{employeeName}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("detailSetup")}</dt>
          <dd>
            {event.setup_stable_id
              ? `${event.setup_stable_id}@${event.setup_version}`
              : t("directComponent")}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("detailProject")}</dt>
          <dd>{event.project_id}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("detailHarness")}</dt>
          <dd>{event.harness}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("detailDevice")}</dt>
          <dd>{event.device_id}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">{t("detailInventory")}</dt>
          <dd>
            {inventory ? `${inventory.coverage} · ${inventory.last_scan_at}` : t("noCurrentScan")}
          </dd>
        </div>
      </dl>
    </article>
  );
}

export async function UsageReportDrawer({
  data,
  detailError,
  eventList,
  detailPage,
  chartQuery,
  employeeId,
  selected,
  detailPageHref,
  focusedObject,
}: DrawerProps) {
  const t = await getTranslations("corporateReports");

  const subtitle =
    selected("detail_day") ||
    (selected("detail_weekday")
      ? t("weekdayHour", {
          weekday: selected("detail_weekday"),
          hour: selected("detail_hour"),
        })
      : focusedObject?.name || selected("detail_id") || t("selectedPeriod"));

  return (
    <Sheet defaultOpen>
      <SheetContent className="w-[min(calc(100vw-1rem),36rem)] overflow-y-auto p-5">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <SheetTitle className="text-xl font-medium">{t("usageDetails")}</SheetTitle>
            <p className="text-muted-foreground mt-1 text-sm">{subtitle}</p>
          </div>
          <SheetClose asChild>
            <Link
              href={`/corporate/reports/usage?${chartQuery}`}
              className="text-muted-foreground text-sm hover:underline"
            >
              {t("close")}
            </Link>
          </SheetClose>
        </div>
        {focusedObject && (
          <FocusedObjectDetails focusedObject={focusedObject} employeeId={employeeId} t={t} />
        )}
        {detailError ? (
          <StatePanel
            kind="error"
            title={detailError === 403 ? t("eventDetailsForbidden") : t("eventDetailsError")}
          />
        ) : eventList?.events.length ? (
          <div className="space-y-3">
            {eventList.events.map((event) => (
              <UsageEventCard
                key={event.event_id}
                event={event}
                employeeName={
                  data.employees.find((row) => row.employee_id === event.employee_id)?.name ??
                  event.employee_id
                }
                inventory={data.inventory_employees.find(
                  (item) => item.employee_id === event.employee_id,
                )}
                t={t}
              />
            ))}
          </div>
        ) : (
          <StatePanel kind="empty" title={t("noRecordedUsesSelection")} />
        )}
        {eventList && (
          <nav aria-label={t("eventPages")} className="mt-5 flex justify-between text-sm">
            {detailPage > 0 ? (
              <Link className="text-primary hover:underline" href={detailPageHref(detailPage - 1)}>
                {t("pagePrevious")}
              </Link>
            ) : (
              <span />
            )}
            {eventList.events.length === 50 && (
              <Link className="text-primary hover:underline" href={detailPageHref(detailPage + 1)}>
                {t("pageNext")}
              </Link>
            )}
          </nav>
        )}
      </SheetContent>
    </Sheet>
  );
}
