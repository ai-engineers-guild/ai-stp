"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/atoms/dialog";
import { revokeDeviceAction } from "@/actions/devices";
import type { DeviceRecord } from "@/lib/api/generated/types.gen";
import { DEVICE_SUMMARY_FIELDS } from "@/lib/api/device-summary-fields";
import { ApiError } from "@/lib/api/errors";
import { browserDeviceLabel } from "@/lib/device-label";
import { Icon } from "@/theme";

type DeviceListProps = {
  devices: DeviceRecord[];
  currentDeviceId: string | null;
  csrfToken: string;
  locale: string;
};

type DeviceCardProps = {
  device: DeviceRecord;
  duplicateCount: number;
  isCurrent: boolean;
  open: boolean;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onRevoke: (device: DeviceRecord) => void;
  locale: string;
};

function deviceGroupKey(device: DeviceRecord): string {
  if (device.device_type === "web") {
    return `web:${browserDeviceLabel(device.user_agent) ?? "browser"}:${device.state}`;
  }
  const summary = device.summary;
  return `cli:${summary?.display_name ?? "cli"}:${summary?.operating_system ?? "unknown"}:${device.state}`;
}

export function groupDevices(devices: DeviceRecord[], currentDeviceId: string | null) {
  const groups = new Map<string, DeviceRecord[]>();
  for (const device of devices) {
    const key = deviceGroupKey(device);
    groups.set(key, [...(groups.get(key) ?? []), device]);
  }
  return [...groups.values()].flatMap((items) => {
    const device =
      items.find((item) => item.device_id === currentDeviceId) ??
      [...items].sort((a, b) => b.last_active_at.localeCompare(a.last_active_at))[0];
    return device ? [{ devices: items, device }] : [];
  });
}

function DeviceCard({
  device,
  duplicateCount,
  isCurrent,
  open,
  pending,
  onOpenChange,
  onRevoke,
  locale,
}: DeviceCardProps) {
  const t = useTranslations("devices");
  const tc = useTranslations("common");
  const summary = device.summary;
  const deviceType = device.device_type === "web" ? "web" : "cli";
  const readableName =
    summary?.display_name ??
    (deviceType === "web" ? browserDeviceLabel(device.user_agent) : null) ??
    t(deviceType === "web" ? "webBrowser" : "cliDevice");
  const location = device.approximate_location ?? null;
  const lastConnected = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(device.last_active_at));

  return (
    <li
      className="border-border bg-card text-card-foreground rounded-lg border p-4 shadow-sm"
      data-device-id={device.device_id}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-lg font-medium tracking-tight">{readableName}</h3>
          <Badge variant="secondary">{device.state}</Badge>
          {isCurrent ? <Badge variant="success">{t("current")}</Badge> : null}
        </div>
        {device.state === "active" ? (
          <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogTrigger asChild>
              <Button variant="destructive" size="sm">
                {t("revoke")}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{t("revokeConfirmTitle")}</DialogTitle>
                <DialogDescription>{t("revokeConfirmBody")}</DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => {
                    onOpenChange(false);
                  }}
                >
                  {tc("cancel")}
                </Button>
                <Button
                  variant="destructive"
                  disabled={pending}
                  onClick={() => {
                    onRevoke(device);
                  }}
                >
                  {tc("confirm")}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        ) : null}
      </div>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground text-xs">{t("connection")}</dt>
          <dd>{t(deviceType === "web" ? "webBrowser" : "cliDevice")}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">{t("lastConnected")}</dt>
          <dd suppressHydrationWarning>{lastConnected}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground text-xs">{t("approximateLocation")}</dt>
          <dd>{location ?? t("locationUnavailable")}</dd>
        </div>
      </dl>
      {summary ? (
        <dl
          className="mt-4 grid gap-2 border-t pt-4 text-sm sm:grid-cols-2"
          data-summary-fields={DEVICE_SUMMARY_FIELDS.join(",")}
        >
          <div>
            <dt className="text-muted-foreground text-xs">{t("displayName")}</dt>
            <dd className="font-medium">{summary.display_name}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground text-xs">{t("os")}</dt>
            <dd className="font-medium capitalize">{summary.operating_system}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground text-xs">{t("architecture")}</dt>
            <dd className="font-mono text-sm font-medium">{summary.architecture}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground text-xs">{t("toolchain")}</dt>
            <dd className="font-mono text-sm font-medium">{summary.toolchain_profile_version}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-muted-foreground text-xs">{t("harnesses")}</dt>
            <dd>
              <ul className="list-disc pl-5 font-mono text-sm">
                {summary.detected_harnesses.map((h) => (
                  <li key={`${h.harness_id}-${h.version}`}>
                    {h.harness_id}@{h.version}
                  </li>
                ))}
              </ul>
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground text-xs">{t("updatedAt")}</dt>
            <dd className="font-mono text-sm">{summary.summary_updated_at}</dd>
          </div>
        </dl>
      ) : null}
      <details className="mt-4 border-t pt-3">
        <summary className="text-muted-foreground cursor-pointer text-xs font-medium">
          {t("technicalDetails")}
        </summary>
        <div className="mt-3 flex min-w-0 flex-wrap items-center gap-2 text-sm">
          {duplicateCount > 1 ? (
            <p className="text-muted-foreground w-full text-xs">
              {t("matchingSessions", { count: duplicateCount })}
            </p>
          ) : null}
          <code className="max-w-full truncate" title={device.device_id}>
            {device.device_id}
          </code>
          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-label={t("copyDeviceId")}
            onClick={() =>
              void navigator.clipboard
                .writeText(device.device_id)
                .then(() => toast.success(tc("copied")))
            }
          >
            <Icon name="copy" size="sm" />
          </Button>
          {device.user_agent ? (
            <p className="text-muted-foreground w-full text-xs break-all">{device.user_agent}</p>
          ) : null}
        </div>
      </details>
    </li>
  );
}

export function DeviceList({ devices, currentDeviceId, csrfToken, locale }: DeviceListProps) {
  const t = useTranslations("devices");
  const tc = useTranslations("common");
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [openId, setOpenId] = useState<string | null>(null);

  function onRevoke(device: DeviceRecord) {
    startTransition(() => {
      void (async () => {
        try {
          const result = await revokeDeviceAction({
            deviceId: device.device_id,
            etag: device.etag,
            csrfToken,
          });
          if (result.operationId) {
            toast.success(t("revoked"), {
              description: `${tc("referenceId")}: ${result.operationId}`,
            });
          } else {
            toast.success(t("revoked"));
          }
          if (result.signedOut) {
            toast.message(t("revokedCurrent"));
            router.push("/login");
            return;
          }
          setOpenId(null);
          router.refresh();
        } catch (error) {
          if (error instanceof ApiError) {
            if (error.code === "AI_STP_PRECONDITION_FAILED") {
              toast.error(t("staleEtag"));
            } else if (error.code === "AI_STP_CONFLICT") {
              toast.error(t("conflict"));
            } else {
              toast.error(error.message);
            }
          } else {
            toast.error(tc("error"));
          }
          router.refresh();
        }
      })();
    });
  }

  if (devices.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("empty")}</p>;
  }

  const groups = groupDevices(devices, currentDeviceId);
  return (
    <ul className="flex flex-col gap-4">
      {groups.map(({ device, devices: matchingDevices }) => (
        <DeviceCard
          key={device.device_id}
          device={device}
          duplicateCount={matchingDevices.length}
          isCurrent={currentDeviceId === device.device_id}
          open={openId === device.device_id}
          pending={pending}
          onOpenChange={(open) => {
            setOpenId(open ? device.device_id : null);
          }}
          onRevoke={onRevoke}
          locale={locale}
        />
      ))}
    </ul>
  );
}
