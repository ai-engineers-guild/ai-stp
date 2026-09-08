"use client";

import { useEffect, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { githubConnect, githubStatus } from "@/actions/github";
import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

export function GitHubConnectionLink({
  csrfToken,
  locale,
  compact = false,
}: {
  csrfToken: string;
  locale: "en" | "ru";
  compact?: boolean;
}) {
  const t = useTranslations("githubConnector");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [error, setError] = useState(false);
  const [busy, start] = useTransition();

  useEffect(() => {
    void githubStatus(csrfToken).then((result) => {
      setConnected(result.ok && result.data.connections.some((item) => item.state === "connected"));
      setError(!result.ok);
    });
  }, [csrfToken]);

  function connect() {
    setError(false);
    start(async () => {
      const result = await githubConnect(csrfToken, {
        purpose: "source",
        locale,
        mode: "install",
        confirmed: true,
      });
      if (result.ok) window.location.assign(result.data.authorization_url);
      else setError(true);
    });
  }

  const statusLabel =
    connected === null ? t("loading") : connected ? t("connected") : t("disconnected");
  const action = connected ? (
    <Button asChild variant="outline" className="min-h-11 shrink-0">
      <Link href="/account/github">{t("manageShort")}</Link>
    </Button>
  ) : (
    <Button
      type="button"
      variant="outline"
      className="min-h-11 shrink-0"
      disabled={busy || connected === null}
      aria-busy={busy}
      title={error ? t("error") : undefined}
      onClick={connect}
    >
      {t("connectShort")}
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
            <span
              aria-hidden="true"
              className={`size-2 rounded-full ${connected ? "bg-success" : "bg-muted-foreground"}`}
            />
            <span>{statusLabel}</span>
          </span>
          {action}
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
    <button
      type="button"
      className={className}
      disabled={busy || connected === null}
      aria-busy={busy}
      title={error ? t("error") : undefined}
      onClick={connect}
    >
      {t("title")} · {t("disconnected")}
    </button>
  );
}
