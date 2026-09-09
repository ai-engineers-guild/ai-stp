"use client";

/* eslint-disable max-lines, max-lines-per-function, complexity -- one compact connector state machine. */

import { useEffect, useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import {
  githubConfirm,
  githubConnect,
  githubDisconnect,
  githubPlan,
  githubStatus,
} from "@/actions/github";
import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/atoms/dialog";
import { Input } from "@/components/atoms/input";
import { Skeleton } from "@/components/atoms/skeleton";
import { HistoryBackButton } from "@/components/molecules/history-back-button";
import { Link } from "@/lib/i18n/navigation";
import {
  navigateGitHubConnectionWindow,
  openGitHubConnectionWindow,
  watchGitHubConnection,
} from "@/lib/github-connection-flow";
import type {
  GitHubActionPlanResponse,
  GitHubConnectorStatus,
  GitHubInstallation,
  GitHubRepository,
} from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";

export function GithubConnector({
  csrfToken,
  deviceId,
  githubIdentityLinked,
  locale,
}: {
  csrfToken: string;
  deviceId: string | null;
  githubIdentityLinked: boolean;
  locale: "en" | "ru";
}) {
  const t = useTranslations("githubConnector");
  const [status, setStatus] = useState<GitHubConnectorStatus | null>(null);
  const [plan, setPlan] = useState<GitHubActionPlanResponse | null>(null);
  const [typedName, setTypedName] = useState("");
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [busy, start] = useTransition();
  const stopPolling = useRef<(() => void) | null>(null);
  const source = status?.connections.find((item) => item.purpose === "source");
  const admin = status?.connections.find((item) => item.purpose === "administration");
  const connected = source?.state === "connected";
  const repositories = uniqueRepositories(source?.repositories ?? [], admin?.repositories ?? []);
  const installations = uniqueInstallations(
    source?.installations ?? [],
    admin?.installations ?? [],
  );
  const identityLinkHref = `/v1/auth/link/github?${new URLSearchParams({
    return_to: `/${locale}/account/github`,
  }).toString()}`;

  useEffect(() => () => stopPolling.current?.(), []);

  function run<T>(
    request: () => Promise<{ ok: true; data: T } | { ok: false; code: string }>,
    done: (data: T) => void,
    failed?: () => void,
  ) {
    setError("");
    start(async () => {
      const result = await request();
      if (result.ok) done(result.data);
      else {
        setError(result.code);
        failed?.();
      }
    });
  }

  function connect(purpose: "source" | "administration", mode: "install" | "authorize") {
    const popup = openGitHubConnectionWindow();
    run(
      () => githubConnect(csrfToken, { purpose, locale, mode, confirmed: true }),
      (result) => {
        navigateGitHubConnectionWindow(popup, result.authorization_url);
        stopPolling.current?.();
        stopPolling.current = watchGitHubConnection(
          popup,
          async () => {
            const current = await githubStatus(csrfToken);
            if (!current.ok) {
              setError(current.code);
              return false;
            }
            setStatus(current.data);
            return current.data.connections.some((item) => item.state === "connected");
          },
          refresh,
        );
      },
      () => popup?.close(),
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

  const connectionLabel = connected
    ? t("connected")
    : source?.state === "reauthorization_required"
      ? t("authorizationRequired")
      : t("disconnected");

  return (
    <div className="min-w-0 space-y-8" aria-busy={busy}>
      <header className="space-y-3">
        <HistoryBackButton label={t("back")} fallback="/account" />
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
          <span
            className={`rounded-full px-3 py-1 text-sm ${connected ? "bg-emerald-100 text-emerald-800" : "bg-muted text-muted-foreground"}`}
          >
            {connectionLabel}
          </span>
        </div>
        <p className="text-muted-foreground max-w-2xl">{t("simpleIntro")}</p>
      </header>

      {error ? (
        <p role="alert" className="text-destructive">
          {t("error")}
        </p>
      ) : null}
      {!status ? <ConnectorSkeleton label={t("loading")} /> : null}
      {busy ? (
        <div className="text-muted-foreground flex items-center gap-2 text-sm" role="status">
          <Icon name="loader" size="sm" className="animate-spin" />
          {t("working")}
        </div>
      ) : null}

      {status && !connected ? (
        <section className="border-border max-w-2xl space-y-4 rounded-lg border p-5">
          <h2 className="text-xl font-medium">{t("connectTitle")}</h2>
          <p className="text-muted-foreground">{t("connectHint")}</p>
          <div className="flex flex-wrap gap-3">
            {githubIdentityLinked ? (
              <>
                <Button
                  disabled={busy || !source?.configured}
                  onClick={() => {
                    connect("source", "authorize");
                  }}
                >
                  {t("authorize")}
                </Button>
                <Button
                  variant="outline"
                  disabled={busy || !source?.configured}
                  onClick={() => {
                    connect("source", "install");
                  }}
                >
                  {t("install")}
                </Button>
              </>
            ) : (
              <Button asChild>
                <a href={identityLinkHref}>{t("linkIdentity")}</a>
              </Button>
            )}
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
          <div className="space-y-3">
            {installations.map((installation) => {
              const isOpen = !collapsed.has(installation.installation_id);
              return (
                <section
                  key={installation.installation_id}
                  className="border-border overflow-hidden rounded-lg border"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <button
                      type="button"
                      className="flex min-w-0 items-center gap-3 text-left"
                      aria-expanded={isOpen}
                      onClick={() => {
                        setCollapsed((current) => {
                          const next = new Set(current);
                          if (next.has(installation.installation_id))
                            next.delete(installation.installation_id);
                          else next.add(installation.installation_id);
                          return next;
                        });
                      }}
                    >
                      <Icon name={isOpen ? "chevronDown" : "chevronRight"} size="sm" />
                      <span className="min-w-0">
                        <span className="block truncate font-medium">
                          {installation.account_login}
                        </span>
                        <span className="text-muted-foreground block text-sm">
                          {installation.account_type === "Organization"
                            ? t("organization")
                            : t("personalProfile")}{" "}
                          {" · "}
                          {t("repositoriesCount", { count: installation.repositories.length })}
                        </span>
                      </span>
                    </button>
                    <a
                      href={installation.account_html_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm underline underline-offset-4"
                    >
                      {t("viewGithubProfile")}
                    </a>
                  </div>
                  {isOpen ? (
                    <ul className="border-border divide-border divide-y border-t">
                      {installation.repositories.map((repository) => (
                        <RepositoryRow
                          key={repository.repository_id}
                          repository={repository}
                          adminConnected={admin?.state === "connected"}
                          busy={busy}
                          deviceId={deviceId}
                          onReview={review}
                          t={t}
                        />
                      ))}
                    </ul>
                  ) : null}
                </section>
              );
            })}
          </div>
        </section>
      ) : null}

      <Dialog
        open={plan?.state === "planned"}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setPlan(null);
            setTypedName("");
          }
        }}
      >
        <DialogContent closeLabel={t("close")}>
          <DialogHeader>
            <DialogTitle>{t("confirmRepositoryTitle")}</DialogTitle>
            <DialogDescription>{t("confirmModalHint")}</DialogDescription>
          </DialogHeader>
          {plan?.state === "planned" ? (
            <>
              <p className="font-medium">{plan.repository.full_name}</p>
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
              <DialogFooter>
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
                  {busy ? <Icon name="loader" size="sm" className="animate-spin" /> : null}
                  {t("confirmAction")}
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => {
                    setPlan(null);
                  }}
                >
                  {t("cancel")}
                </Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ConnectorSkeleton({ label }: { label: string }) {
  return (
    <div className="space-y-3" role="status" aria-label={label} aria-busy="true">
      <Skeleton className="h-5 w-48" />
      <Skeleton className="h-16 w-full rounded-lg" />
      <Skeleton className="h-16 w-full rounded-lg" />
    </div>
  );
}

function RepositoryRow({
  repository,
  adminConnected,
  busy,
  deviceId,
  onReview,
  t,
}: {
  repository: GitHubRepository;
  adminConnected: boolean;
  busy: boolean;
  deviceId: string | null;
  onReview: (repository: GitHubRepository) => void;
  t: ReturnType<typeof useTranslations<"githubConnector">>;
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-4 p-4">
      <div className="min-w-0 flex-1">
        <a
          href={repository.html_url}
          target="_blank"
          rel="noreferrer"
          className="focus-visible:ring-ring block min-w-0 rounded-sm focus-visible:ring-2 focus-visible:outline-none"
        >
          <p className="truncate font-medium underline-offset-4 hover:underline">
            {repository.full_name}
          </p>
          <p className="text-muted-foreground text-sm">
            {repository.private ? t("privateRepository") : t("publicRepository")}
          </p>
        </a>
        {repository.platform_objects.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {repository.platform_objects.map((object) => (
              <Link
                key={`${object.object_kind}:${object.stable_id}:${object.version}`}
                href={`/objects/${object.object_kind}/${object.stable_id}`}
                className="border-border bg-muted hover:bg-accent inline-flex items-center gap-2 rounded-sm border px-2 py-1 text-xs"
              >
                <span>{object.name}</span>
                <span className="text-muted-foreground">{object.visibility}</span>
              </Link>
            ))}
          </div>
        ) : null}
      </div>
      {adminConnected && repository.can_administer ? (
        <Button
          variant="outline"
          disabled={busy || !deviceId}
          onClick={() => {
            onReview(repository);
          }}
        >
          {repository.private ? t("makeRepositoryPublic") : t("makeRepositoryPrivate")}
        </Button>
      ) : null}
    </li>
  );
}

function uniqueRepositories(...groups: GitHubRepository[][]): GitHubRepository[] {
  return [
    ...new Map(
      groups.flat().map((repository) => [repository.repository_id, repository] as const),
    ).values(),
  ];
}

function uniqueInstallations(...groups: GitHubInstallation[][]): GitHubInstallation[] {
  const merged = new Map<number, GitHubInstallation>();
  for (const installation of groups.flat()) {
    const current = merged.get(installation.installation_id);
    if (!current) {
      merged.set(installation.installation_id, installation);
      continue;
    }
    merged.set(installation.installation_id, {
      ...current,
      repositories: uniqueRepositories(current.repositories, installation.repositories),
    });
  }
  return [...merged.values()];
}
