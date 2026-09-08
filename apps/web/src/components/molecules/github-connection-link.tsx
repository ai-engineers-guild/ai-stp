"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { githubStatus } from "@/actions/github";
import { Link } from "@/lib/i18n/navigation";

export function GitHubConnectionLink({ csrfToken }: { csrfToken: string }) {
  const t = useTranslations("githubConnector");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    void githubStatus(csrfToken).then((result) => {
      setConnected(result.ok && result.data.connections.some((item) => item.state === "connected"));
    });
  }, [csrfToken]);

  return (
    <Link
      href="/account/github"
      className={`inline-flex min-h-11 items-center rounded-md border px-4 text-sm font-medium ${
        connected
          ? "border-emerald-300 bg-emerald-100 text-emerald-900 hover:bg-emerald-200"
          : "border-border bg-muted text-muted-foreground hover:bg-muted/80"
      }`}
    >
      {t("title")} · {connected ? t("connected") : t("disconnected")}
    </Link>
  );
}
