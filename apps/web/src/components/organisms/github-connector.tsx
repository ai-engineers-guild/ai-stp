"use client";

/* eslint-disable max-lines-per-function, complexity -- one compact connector state machine. */

import { useEffect, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import {
  githubConfirm,
  githubConnect,
  githubDisconnect,
  githubPlan,
  githubStatus,
} from "@/actions/github";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import type {
  GitHubActionPlanResponse,
  GitHubConnectorStatus,
  GitHubRepository,
} from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";

export function GithubConnector({
  csrfToken,
  deviceId,
  locale,
}: {
  csrfToken: string;
  deviceId: string | null;
  locale: "en" | "ru";
}) {
  const t = useTranslations("githubConnector");
  const [status, setStatus] = useState<GitHubConnectorStatus | null>(null);
  const [plan, setPlan] = useState<GitHubActionPlanResponse | null>(null);
  const [typedName, setTypedName] = useState("");
  const [error, setError] = useState("");
  const [busy, start] = useTransition();
  const source = status?.connections.find((item) => item.purpose === "source");
  const admin = status?.connections.find((item) => item.purpose === "administration");
  const connected = source?.state === "connected";
  const repositories = uniqueRepositories(source?.repositories ?? [], admin?.repositories ?? []);

  function run<T>(
    request: () => Promise<{ ok: true; data: T } | { ok: false; code: string }>,
    done: (data: T) => void,
  ) {
    setError("");
    start(async () => {
      const result = await request();
      if (result.ok) done(result.data);
      else setError(result.code);
    });
  }

  function connect(purpose: "source" | "administration", mode: "install" | "authorize") {
    run(
      () => githubConnect(csrfToken, { purpose, locale, mode, confirmed: true }),
      (result) => {
        window.location.assign(result.authorization_url);
      },
    );
  }

  function review(repository: GitHubRepository) {
    if (!deviceId) return;
    run(
      () =>
        githubPlan(csrfToken, {
          action: repository.private ? "make_public" : "make_private",
          installation_id: repository.installation_id,
          repository_id: repository.repository_id,
          recipient: null,
          permission: null,
          device_id: deviceId,
          idempotency_key: crypto.randomUUID(),
        }),
      (result) => {
        setPlan(result);
        setTypedName("");
      },
    );
  }

  function refresh() {
    void githubStatus(csrfToken).then((result) => {
      if (result.ok) setStatus(result.data);
      else setError(result.code);
    });
  }

  useEffect(refresh, [csrfToken]);

  return (
    <div className="min-w-0 space-y-8" aria-busy={busy}>
      <header className="space-y-3">
        <Link href="/account" className="underline underline-offset-4">
          {t("back")}
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
          <span
            className={`rounded-full px-3 py-1 text-sm ${connected ? "bg-emerald-100 text-emerald-800" : "bg-muted text-muted-foreground"}`}
          >
            {connected ? t("connected") : t("disconnected")}
          </span>
        </div>
        <p className="text-muted-foreground max-w-2xl">{t("simpleIntro")}</p>
      </header>

      {error ? (
        <p role="alert" className="text-destructive">
          {t("error")}
        </p>
      ) : null}
      {!status ? <p role="status">{t("loading")}</p> : null}

      {status && !connected ? (
        <section className="border-border max-w-2xl space-y-4 rounded-lg border p-5">
          <h2 className="text-xl font-medium">{t("connectTitle")}</h2>
          <p className="text-muted-foreground">{t("connectHint")}</p>
          <div className="flex flex-wrap gap-3">
            <Button
              disabled={busy || !source?.configured}
              onClick={() => {
                connect("source", "install");
              }}
            >
              {t("connect")}
            </Button>
            <Button
              variant="ghost"
              disabled={busy || !source?.configured}
              onClick={() => {
                connect("source", "authorize");
              }}
            >
              {t("alreadyInstalled")}
            </Button>
          </div>
        </section>
      ) : null}

      {connected ? (
        <section className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-medium">{t("repositoriesTitle")}</h2>
              <p className="text-muted-foreground text-sm">
                {t("repositoriesCount", { count: repositories.length })}
              </p>
            </div>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                run(
                  () => githubDisconnect(csrfToken, { purpose: "source", confirmed: true }),
                  setStatus,
                );
              }}
            >
              {t("disconnect")}
            </Button>
          </div>
          {admin?.state !== "connected" ? (
            <div className="border-border flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4">
              <p className="text-muted-foreground text-sm">{t("managementHint")}</p>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  connect("administration", "authorize");
                }}
              >
                {t("enableManagement")}
              </Button>
            </div>
          ) : null}
          <ul className="border-border divide-border divide-y rounded-lg border">
            {repositories.map((repository) => (
              <li
                key={repository.repository_id}
                className="flex min-h-16 flex-wrap items-center justify-between gap-3 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{repository.full_name}</p>
                  <p className="text-muted-foreground text-sm">
                    {repository.private ? t("privateRepository") : t("publicRepository")}
                  </p>
                </div>
                {admin?.state === "connected" && repository.can_administer ? (
                  <Button
                    variant="outline"
                    disabled={busy || !deviceId}
                    onClick={() => {
                      review(repository);
                    }}
                  >
                    {repository.private ? t("makeRepositoryPublic") : t("makeRepositoryPrivate")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {plan?.state === "planned" ? (
        <section className="border-border max-w-2xl space-y-4 rounded-lg border p-5">
          <h2 className="text-xl font-medium">{t("confirmRepositoryTitle")}</h2>
          <p>{plan.repository.full_name}</p>
          <p className="text-muted-foreground text-sm">
            {t(
              plan.action === "make_public"
                ? "repository_and_history_public"
                : "repository_private",
            )}
          </p>
          <label className="block space-y-2 text-sm">
            {t("typeName")}
            <Input
              value={typedName}
              onChange={(event) => {
                setTypedName(event.target.value);
              }}
              autoComplete="off"
            />
          </label>
          <div className="flex gap-3">
            <Button
              variant={plan.action === "make_public" ? "default" : "destructive"}
              disabled={busy || typedName !== plan.repository.full_name}
              onClick={() => {
                run(
                  () =>
                    githubConfirm(csrfToken, plan.plan_id, {
                      plan_hash: plan.plan_hash,
                      confirmed: true,
                      typed_repository_name: typedName,
                      idempotency_key: crypto.randomUUID(),
                    }),
                  (result) => {
                    setPlan(result);
                    refresh();
                  },
                );
              }}
            >
              {t("confirmAction")}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setPlan(null);
              }}
            >
              {t("cancel")}
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function uniqueRepositories(...groups: GitHubRepository[][]): GitHubRepository[] {
  return [
    ...new Map(groups.flat().map((repository) => [repository.repository_id, repository])).values(),
  ];
}
