"use client";

/* eslint-disable max-lines, max-lines-per-function, complexity -- one compact connector state machine. */

import { useEffect, useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import {
  gitlabConfirm,
  gitlabConnect,
  gitlabDisconnect,
  gitlabPlan,
  gitlabStatus,
} from "@/actions/gitlab";
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
  GitLabActionPlanRequest,
  GitLabActionPlanResponse,
  GitLabConnectorRepository,
  GitLabConnectorStatus,
} from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";

type PlanRequest =
  | { kind: "visibility"; repository: GitLabConnectorRepository }
  | { kind: "access"; repository: GitLabConnectorRepository; revoke: boolean }
  | { kind: "create" };

const ACCESS_LEVELS = ["guest", "reporter", "developer", "maintainer"] as const;

export function GitLabConnector({
  csrfToken,
  organizationId,
  deviceId,
  gitlabIdentityLinked,
  locale,
  capabilities,
}: {
  csrfToken: string;
  organizationId: string;
  deviceId: string | null;
  gitlabIdentityLinked: boolean;
  locale: "en" | "ru";
  capabilities: readonly string[];
}) {
  const t = useTranslations("gitlabConnector");
  const [status, setStatus] = useState<GitLabConnectorStatus | null>(null);
  const [plan, setPlan] = useState<GitLabActionPlanResponse | null>(null);
  const [draft, setDraft] = useState<PlanRequest | null>(null);
  const [typedName, setTypedName] = useState("");
  const [recipient, setRecipient] = useState("");
  const [accessLevel, setAccessLevel] = useState<(typeof ACCESS_LEVELS)[number]>("developer");
  const [repoName, setRepoName] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [repoVisibility, setRepoVisibility] = useState<"private" | "internal" | "public">(
    "private",
  );
  const [error, setError] = useState("");
  const [busy, start] = useTransition();
  const stopPolling = useRef<(() => void) | null>(null);
  const source = status?.connections.find((item) => item.purpose === "source");
  const admin = status?.connections.find((item) => item.purpose === "administration");
  const connected = source?.state === "connected";
  const repositories = source?.repositories ?? [];
  const canAccess = capabilities.includes("connector.gitlab.access");
  const canVisibility = capabilities.includes("connector.gitlab.visibility");
  const canCreate = capabilities.includes("connector.gitlab.create");
  const levelLabels = {
    guest: t("level_guest"),
    reporter: t("level_reporter"),
    developer: t("level_developer"),
    maintainer: t("level_maintainer"),
  } as const;
  const visibilityLabels = {
    private: t("visibility_private"),
    internal: t("visibility_internal"),
    public: t("visibility_public"),
  } as const;
  const warningLabels = {
    repository_and_history_public: t("warning_repository_and_history_public"),
    repository_private: t("warning_repository_private"),
    repository_internal: t("warning_repository_internal"),
    repository_access: t("warning_repository_access"),
    repository_access_revoked: t("warning_repository_access_revoked"),
    repository_created: t("warning_repository_created"),
  } as const;
  const identityLinkHref = `/v1/auth/link/gitlab?${new URLSearchParams({
    return_to: `/${locale}/corporate/gitlab`,
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

  function connect(purpose: "source" | "administration") {
    const popup = openGitHubConnectionWindow();
    run(
      () => gitlabConnect(csrfToken, organizationId, { purpose, locale, confirmed: true }),
      (result) => {
        navigateGitHubConnectionWindow(popup, result.authorization_url);
        stopPolling.current?.();
        stopPolling.current = watchGitHubConnection(
          popup,
          async () => {
            const current = await gitlabStatus(csrfToken, organizationId);
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

  function refresh() {
    void gitlabStatus(csrfToken, organizationId)
      .then((result) => {
        if (result.ok) setStatus(result.data);
        else setError(result.code);
      })
      .catch(() => {
        setError("unavailable");
      });
  }

  useEffect(refresh, [csrfToken, organizationId]);

  function submitDraft() {
    if (!deviceId || !draft) return;
    const base = { device_id: deviceId, idempotency_key: crypto.randomUUID() };
    const body: GitLabActionPlanRequest =
      draft.kind === "visibility"
        ? {
            ...base,
            action: draft.repository.visibility === "public" ? "make_private" : "make_public",
            project_id: draft.repository.project_id,
          }
        : draft.kind === "access"
          ? {
              ...base,
              action: draft.revoke ? "revoke_access" : "grant_access",
              project_id: draft.repository.project_id,
              recipient,
              ...(draft.revoke ? {} : { access_level: accessLevel }),
            }
          : {
              ...base,
              action: "create_repository" as const,
              name: repoName,
              path: repoPath,
              target_visibility: repoVisibility,
            };
    run(
      () => gitlabPlan(csrfToken, organizationId, body),
      (result) => {
        setPlan(result);
        setTypedName("");
      },
    );
  }

  const connectionLabel = connected
    ? t("connected")
    : source?.state === "reauthorization_required"
      ? t("authorizationRequired")
      : t("disconnected");

  return (
    <div className="min-w-0 space-y-8" aria-busy={busy}>
      <header className="space-y-3">
        <HistoryBackButton
          label={t("backToSettings")}
          fallback="/corporate/organization/admins/settings"
        />
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
      {status && !status.connections.some((item) => item.configured) ? (
        <p className="text-muted-foreground max-w-2xl">{t("unavailable")}</p>
      ) : null}
      {busy ? (
        <div className="text-muted-foreground flex items-center gap-2 text-sm" role="status">
          <Icon name="loader" size="sm" className="animate-spin" />
          {t("working")}
        </div>
      ) : null}

      {status && !connected && source?.configured ? (
        <section className="border-border max-w-2xl space-y-4 rounded-lg border p-5">
          <h2 className="text-xl font-medium">{t("connectTitle")}</h2>
          <p className="text-muted-foreground">{t("connectHint")}</p>
          <div className="flex flex-wrap gap-3">
            {gitlabIdentityLinked ? (
              <Button
                disabled={busy || !source.configured}
                onClick={() => {
                  connect("source");
                }}
              >
                {t("authorize")}
              </Button>
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
              <h2 className="text-xl font-medium">{t("projectsTitle")}</h2>
              <p className="text-muted-foreground text-sm">
                {t("projectsCount", { count: repositories.length })}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {admin?.state === "connected" && canCreate ? (
                <Button
                  variant="outline"
                  disabled={busy || !deviceId}
                  onClick={() => {
                    setDraft({ kind: "create" });
                    setRepoName("");
                    setRepoPath("");
                    setRepoVisibility("private");
                  }}
                >
                  {t("createRepository")}
                </Button>
              ) : null}
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  run(
                    () =>
                      gitlabDisconnect(csrfToken, organizationId, {
                        purpose: "source",
                        confirmed: true,
                      }),
                    setStatus,
                  );
                }}
              >
                {t("disconnect")}
              </Button>
            </div>
          </div>
          {admin?.state !== "connected" && admin?.configured ? (
            <div className="border-border flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4">
              <p className="text-muted-foreground text-sm">{t("managementHint")}</p>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  connect("administration");
                }}
              >
                {t("enableManagement")}
              </Button>
            </div>
          ) : null}
          <ul className="border-border divide-border divide-y rounded-lg border">
            {repositories.map((repository) => (
              <RepositoryRow
                key={repository.project_id}
                repository={repository}
                adminConnected={admin?.state === "connected"}
                canAccess={canAccess}
                canVisibility={canVisibility}
                busy={busy}
                deviceId={deviceId}
                onDraft={(next) => {
                  setDraft(next);
                  setRecipient("");
                  setAccessLevel("developer");
                }}
                t={t}
              />
            ))}
          </ul>
        </section>
      ) : null}

      <Dialog
        open={draft !== null && plan === null}
        onOpenChange={(open) => {
          if (!open && !busy) setDraft(null);
        }}
      >
        <DialogContent closeLabel={t("close")}>
          <DialogHeader>
            <DialogTitle>{t("actionTitle")}</DialogTitle>
            <DialogDescription>{t("actionHint")}</DialogDescription>
          </DialogHeader>
          {draft?.kind === "access" ? (
            <div className="space-y-3">
              <p className="font-medium">{draft.repository.path_with_namespace}</p>
              <label className="block space-y-2 text-sm">
                {t("recipient")}
                <Input
                  value={recipient}
                  onChange={(event) => {
                    setRecipient(event.target.value);
                  }}
                  autoComplete="off"
                />
              </label>
              {!draft.revoke ? (
                <label className="block space-y-2 text-sm">
                  {t("accessLevel")}
                  <select
                    className="border-border bg-background block w-full rounded-md border px-3 py-2"
                    value={accessLevel}
                    onChange={(event) => {
                      setAccessLevel(event.target.value as (typeof ACCESS_LEVELS)[number]);
                    }}
                  >
                    {ACCESS_LEVELS.map((level) => (
                      <option key={level} value={level}>
                        {levelLabels[level]}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>
          ) : null}
          {draft?.kind === "create" ? (
            <div className="space-y-3">
              <label className="block space-y-2 text-sm">
                {t("repositoryName")}
                <Input
                  value={repoName}
                  onChange={(event) => {
                    setRepoName(event.target.value);
                  }}
                  autoComplete="off"
                />
              </label>
              <label className="block space-y-2 text-sm">
                {t("repositoryPath")}
                <Input
                  value={repoPath}
                  onChange={(event) => {
                    setRepoPath(event.target.value);
                  }}
                  autoComplete="off"
                />
              </label>
              <label className="block space-y-2 text-sm">
                {t("targetVisibility")}
                <select
                  className="border-border bg-background block w-full rounded-md border px-3 py-2"
                  value={repoVisibility}
                  onChange={(event) => {
                    setRepoVisibility(event.target.value as "private" | "internal" | "public");
                  }}
                >
                  {(["private", "internal", "public"] as const).map((value) => (
                    <option key={value} value={value}>
                      {visibilityLabels[value]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ) : null}
          <DialogFooter>
            <Button
              disabled={
                busy ||
                !deviceId ||
                (draft?.kind === "access" && !recipient) ||
                (draft?.kind === "create" && (!repoName || !repoPath))
              }
              onClick={submitDraft}
            >
              {t("reviewAction")}
            </Button>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setDraft(null);
              }}
            >
              {t("cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={plan?.state === "planned"}
        onOpenChange={(open) => {
          if (!open && !busy) {
            setPlan(null);
            setDraft(null);
            setTypedName("");
          }
        }}
      >
        <DialogContent closeLabel={t("close")}>
          <DialogHeader>
            <DialogTitle>{t("confirmTitle")}</DialogTitle>
            <DialogDescription>{t("confirmModalHint")}</DialogDescription>
          </DialogHeader>
          {plan?.state === "planned" ? (
            <>
              <p className="font-medium">{plan.path_with_namespace ?? plan.path ?? plan.name}</p>
              <p className="text-muted-foreground text-sm">{warningLabels[plan.warning]}</p>
              {plan.action === "make_public" || plan.action === "make_private" ? (
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
              ) : null}
              <DialogFooter>
                <Button
                  variant={plan.action === "make_public" ? "default" : "destructive"}
                  disabled={
                    busy ||
                    ((plan.action === "make_public" || plan.action === "make_private") &&
                      typedName !== plan.path_with_namespace)
                  }
                  onClick={() => {
                    run(
                      () =>
                        gitlabConfirm(csrfToken, organizationId, plan.plan_id, {
                          plan_hash: plan.plan_hash,
                          confirmed: true,
                          typed_project_path:
                            plan.action === "make_public" || plan.action === "make_private"
                              ? typedName
                              : null,
                          idempotency_key: crypto.randomUUID(),
                        }),
                      (result) => {
                        setPlan(result);
                        setDraft(null);
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
                    setDraft(null);
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
  canAccess,
  canVisibility,
  busy,
  deviceId,
  onDraft,
  t,
}: {
  repository: GitLabConnectorRepository;
  adminConnected: boolean;
  canAccess: boolean;
  canVisibility: boolean;
  busy: boolean;
  deviceId: string | null;
  onDraft: (draft: PlanRequest) => void;
  t: ReturnType<typeof useTranslations<"gitlabConnector">>;
}) {
  const visibilityLabel =
    repository.visibility === "public"
      ? t("publicRepository")
      : repository.visibility === "internal"
        ? t("internalRepository")
        : t("privateRepository");
  return (
    <li className="flex flex-wrap items-center justify-between gap-4 p-4">
      <div className="min-w-0 flex-1">
        <a
          href={repository.repository_url}
          target="_blank"
          rel="noreferrer"
          className="focus-visible:ring-ring block min-w-0 rounded-sm focus-visible:ring-2 focus-visible:outline-none"
        >
          <p className="truncate font-medium underline-offset-4 hover:underline">
            {repository.path_with_namespace}
          </p>
          <p className="text-muted-foreground text-sm">{visibilityLabel}</p>
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
      {adminConnected ? (
        <div className="flex flex-wrap gap-2">
          {canVisibility ? (
            <Button
              variant="outline"
              disabled={busy || !deviceId}
              onClick={() => {
                onDraft({ kind: "visibility", repository });
              }}
            >
              {repository.visibility === "public"
                ? t("makeRepositoryPrivate")
                : t("makeRepositoryPublic")}
            </Button>
          ) : null}
          {canAccess ? (
            <>
              <Button
                variant="outline"
                disabled={busy || !deviceId}
                onClick={() => {
                  onDraft({ kind: "access", repository, revoke: false });
                }}
              >
                {t("grantAccess")}
              </Button>
              <Button
                variant="outline"
                disabled={busy || !deviceId}
                onClick={() => {
                  onDraft({ kind: "access", repository, revoke: true });
                }}
              >
                {t("revokeAccess")}
              </Button>
            </>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
