"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { githubStatus } from "@/actions/github";
import { Button } from "@/components/atoms/button";
import { Skeleton } from "@/components/atoms/skeleton";
import { Link } from "@/lib/i18n/navigation";
import type { GitHubConnectionStatus } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";

export function GitHubConnectionLink({
  csrfToken,
  compact = false,
}: {
  csrfToken: string;
  compact?: boolean;
}) {
  const t = useTranslations("githubConnector");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [connectionState, setConnectionState] = useState<GitHubConnectionStatus["state"] | null>(
    null,
  );
  const [error, setError] = useState(false);

  useEffect(() => {
    void githubStatus(csrfToken).then((result) => {
      const source = result.ok
        ? result.data.connections.find((item) => item.purpose === "source")
        : undefined;
      setConnectionState(source?.state ?? (result.ok ? "disconnected" : null));
      setConnected(source?.state === "connected");
      setError(!result.ok);
    });
  }, [csrfToken]);

  const statusLabel =
    connectionState === null
      ? t("loading")
      : connectionState === "connected"
        ? t("connected")
        : connectionState === "reauthorization_required"
          ? t("authorizationRequired")
          : t("disconnected");
  const checking = connectionState === null && !error;
  const action = connected ? (
    <Button asChild variant="outline" className="min-h-11 shrink-0">
      <Link href="/account/github">{t("manageShort")}</Link>
    </Button>
  ) : (
    <Button asChild variant="outline" className="min-h-11 shrink-0">
      <Link href="/account/github">{t("connectShort")}</Link>
    </Button>
  );

  if (compact) {
    return (
      <div className="border-border bg-background flex min-w-0 flex-wrap items-center gap-3 rounded-lg border p-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="bg-muted text-foreground grid size-10 shrink-0 place-items-center rounded-full">
            <Icon name="github" size="md" />
          </span>
          <span className="truncate text-sm font-medium">{t("title")}</span>
        </div>
        <div className="ml-auto flex items-center gap-3">
          <span
            role="status"
            aria-live="polite"
            className={`inline-flex items-center gap-2 text-sm ${
              connected ? "text-success" : "text-muted-foreground"
            }`}
          >
            {checking ? (
              <Icon name="loader" size="sm" className="animate-spin" />
            ) : (
              <span
                aria-hidden="true"
                className={`size-2 rounded-full ${connected ? "bg-success" : "bg-muted-foreground"}`}
              />
            )}
            <span>{statusLabel}</span>
          </span>
          {checking ? <Skeleton className="h-11 w-24 shrink-0" /> : action}
          {error ? (
            <span role="alert" className="text-destructive text-xs">
              {t("error")}
            </span>
          ) : null}
        </div>
      </div>
    );
  }

  const className = `inline-flex min-h-11 items-center rounded-md border px-4 text-sm font-medium ${
    connected
      ? "border-success bg-success/10 text-success hover:bg-success/20"
      : "border-border bg-muted text-muted-foreground hover:bg-muted/80"
  }`;
  if (connected) {
    return (
      <Link href="/account/github" className={className}>
        {t("title")} · {t("connected")}
      </Link>
    );
  }
  return (
    <Link href="/account/github" className={className}>
      {checking ? <Icon name="loader" size="sm" className="mr-2 animate-spin" /> : null}
      {t("title")} · {statusLabel}
    </Link>
  );
}
