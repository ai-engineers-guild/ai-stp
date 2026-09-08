"use client";

// Operate: extend account settings with separate source access and reviewed exposure.
// Existing tokens and native controls remain authoritative; no new visual system.
import { useEffect, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Link } from "@/lib/i18n/navigation";
import {
  githubStatus,
  githubConnect,
  githubDisconnect,
  githubPrepare,
  githubPlan,
  githubActionStatus,
  githubConfirm,
  visibilityPlan,
  visibilityConfirm,
} from "@/actions/github";
import type {
  GitHubConnectorStatus,
  GitHubActionPlanResponse,
  GitHubSourcePrepared,
  VisibilityPlanResponse,
} from "@/lib/api/generated/types.gen";

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
  const [error, setError] = useState("");
  const [busy, start] = useTransition();
  const [sourceChoice, setSourceChoice] = useState("");
  const [adminChoice, setAdminChoice] = useState("");
  const [prepared, setPrepared] = useState<GitHubSourcePrepared | null>(null);
  const [plan, setPlan] = useState<GitHubActionPlanResponse | null>(null);
  const [promotion, setPromotion] = useState<VisibilityPlanResponse | null>(null);
  const [typedName, setTypedName] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [promotionConfirmed, setPromotionConfirmed] = useState(false);
  const [disconnecting, setDisconnecting] = useState<"source" | "administration" | null>(null);
  const sources = status?.connections.find((c) => c.purpose === "source")?.repositories ?? [];
  const admins =
    status?.connections
      .find((c) => c.purpose === "administration")
      ?.repositories.filter((r) => r.can_administer) ?? [];
  const source = sources.find((r) => `${r.installation_id}:${r.repository_id}` === sourceChoice);
  const admin = admins.find((r) => `${r.installation_id}:${r.repository_id}` === adminChoice);

  function run<T>(
    operation: () => Promise<{ ok: true; data: T } | { ok: false; code: string; reason?: string }>,
    done: (data: T) => void,
  ) {
    setError("");
    start(async () => {
      try {
        const result = await operation();
        if (result.ok) done(result.data);
        else setError(result.reason && t.has(`errors.${result.reason}`) ? result.reason : result.code);
      } catch {
        setError("AI_STP_UNAVAILABLE");
      }
    });
  }
  useEffect(() => {
    let active = true;
    void githubStatus(csrfToken)
      .then((result) => {
        if (!active) return;
        if (result.ok) setStatus(result.data);
        else setError(result.code);
      })
      .catch(() => {
        if (active) setError("AI_STP_UNAVAILABLE");
      });
    return () => {
      active = false;
    };
  }, [csrfToken]);

  return (
    <div className="min-w-0 space-y-8 [&_button]:min-h-11 [&_button]:whitespace-normal" aria-busy={busy}>
      <header className="space-y-3">
        <Link href="/account" className="underline underline-offset-4">
          {t("back")}
        </Link>
        <h1 className="text-2xl font-medium tracking-tight sm:text-3xl">{t("title")}</h1>
        <p className="text-muted-foreground max-w-prose">{t("intro")}</p>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => run(() => githubStatus(csrfToken), setStatus)}
        >
          {t("refresh")}
        </Button>
      </header>
      {error && (
        <p role="alert">
          {t.has(`errors.${error}`) ? t(`errors.${error}`) : t("error")}
        </p>
      )}
      {!status && !error && <p role="status">{t("loading")}</p>}
      {status?.connections.map((connection) => (
        <section key={connection.purpose} className="border-border space-y-3 border-t pt-6">
          <h2 className="text-xl font-medium">{t(connection.purpose)}</h2>
          <p role="status">{t(connection.state)}</p>
          {connection.reason && t.has(`errors.${connection.reason}`) && (
            <p role="alert">{t(`errors.${connection.reason}`)}</p>
          )}
          <p className="text-muted-foreground max-w-prose">
            {t(connection.purpose === "source" ? "readScope" : "adminScope")}
          </p>
          {!connection.configured ? (
            <p>{t("unconfigured")}</p>
          ) : (
            <div className="flex flex-wrap gap-3">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() =>
                  run(
                    () =>
                      githubConnect(csrfToken, {
                        purpose: connection.purpose,
                        locale,
                        mode: "install",
                        confirmed: true,
                      }),
                    (value) => {
                      const url = new URL(value.authorization_url);
                      if (url.origin === "https://github.com") window.location.assign(url.href);
                    },
                  )
                }
              >
                {t("connect")}
              </Button>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() =>
                  run(
                    () =>
                      githubConnect(csrfToken, {
                        purpose: connection.purpose,
                        locale,
                        mode: "authorize",
                        confirmed: true,
                      }),
                    (value) => {
                      const url = new URL(value.authorization_url);
                      if (url.origin === "https://github.com") window.location.assign(url.href);
                    },
                  )
                }
              >
                {t("authorize")}
              </Button>
              {connection.state !== "disconnected" && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => setDisconnecting(connection.purpose)}
                >
                  {t("disconnect")}
                </Button>
              )}
            </div>
          )}
          {disconnecting === connection.purpose && (
            <div className="space-y-3">
              <p>{t("disconnectWarning")}</p>
              <Button
                variant="destructive"
                disabled={busy}
                onClick={() =>
                  run(
                    () =>
                      githubDisconnect(csrfToken, { purpose: connection.purpose, confirmed: true }),
                    (value) => {
                      setStatus(value);
                      setDisconnecting(null);
                      setPlan(null);
                      setPrepared(null);
                    },
                  )
                }
              >
                {t("confirmDisconnect")}
              </Button>
              <Button variant="ghost" onClick={() => setDisconnecting(null)}>
                {t("cancel")}
              </Button>
            </div>
          )}
        </section>
      ))}
      <section className="border-border space-y-4 border-t pt-6">
        <h2 className="text-xl font-medium">{t("prepareTitle")}</h2>
        <p className="text-muted-foreground max-w-prose">{t("prepareHint")}</p>
        <form
          className="max-w-xl space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!source) return;
            const form = new FormData(event.currentTarget);
            run(
              () =>
                githubPrepare(csrfToken, {
                  installation_id: source.installation_id,
                  repository_id: source.repository_id,
                  commit: String(form.get("commit")),
                  subpath: String(form.get("subpath")),
                  idempotency_key: crypto.randomUUID(),
                }),
              setPrepared,
            );
          }}
        >
          <label className="block space-y-2">
            {t("repository")}
            <select
              className="border-input bg-background min-h-11 w-full rounded-sm border px-3"
              required
              value={sourceChoice}
              onChange={(e) => {
                setSourceChoice(e.target.value);
                setPrepared(null);
              }}
            >
              <option value="">{t("selectRepository")}</option>
              {sources.map((r) => (
                <option
                  key={`${r.installation_id}:${r.repository_id}`}
                  value={`${r.installation_id}:${r.repository_id}`}
                >
                  {r.full_name}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-2">
            {t("commit")}
            <Input name="commit" required pattern="[0-9a-f]{40}" maxLength={40} />
          </label>
          <label className="block space-y-2">
            {t("subpath")}
            <Input name="subpath" required maxLength={512} />
          </label>
          <Button type="submit" variant="outline" disabled={busy || !source}>
            {t("prepare")}
          </Button>
        </form>
        {prepared && (
          <div role="status" className="space-y-2">
            <p>{t("prepared")}</p>
            <pre className="bg-muted overflow-x-auto rounded-sm p-3 text-sm">
              {JSON.stringify(prepared, null, 2)}
            </pre>
            <p className="text-muted-foreground max-w-prose">{t("cliHint")}</p>
            <code className="block break-all">{`ai-stp publication plan --id <component-id> --version <X.Y> --component-root <path> --source-binding-id ${prepared.source_binding_id} --visibility private --json`}</code>
          </div>
        )}
      </section>
      <section className="border-border space-y-4 border-t pt-6">
        <h2 className="text-xl font-medium">{t("actionsTitle")}</h2>
        <p className="text-muted-foreground max-w-prose">{t("grantHint")}</p>
        {!deviceId && <p>{t("deviceRequired")}</p>}
        <form
          className="max-w-xl space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!admin || !deviceId) return;
            const form = new FormData(
              event.currentTarget,
              (event.nativeEvent as SubmitEvent).submitter,
            );
            const action =
              form.get("action") === "invite_collaborator" ? "invite_collaborator" : "make_public";
            run(
              () =>
                githubPlan(csrfToken, {
                  action,
                  installation_id: admin.installation_id,
                  repository_id: admin.repository_id,
                  recipient:
                    action === "invite_collaborator" ? String(form.get("recipient")) : null,
                  permission:
                    action === "invite_collaborator"
                      ? admin.owner_type === "User"
                        ? "push"
                        : "pull"
                      : null,
                  device_id: deviceId,
                  idempotency_key: crypto.randomUUID(),
                }),
              (value) => {
                setPlan(value);
                setTypedName("");
                setConfirmed(false);
              },
            );
          }}
        >
          <label className="block space-y-2">
            {t("repository")}
            <select
              required
              value={adminChoice}
              className="border-input bg-background min-h-11 w-full rounded-sm border px-3"
              onChange={(e) => {
                setAdminChoice(e.target.value);
                setPlan(null);
              }}
            >
              <option value="">{t("selectRepository")}</option>
              {admins.map((r) => (
                <option
                  key={`${r.installation_id}:${r.repository_id}`}
                  value={`${r.installation_id}:${r.repository_id}`}
                >
                  {r.full_name}
                </option>
              ))}
            </select>
          </label>
          {admin?.owner_type === "User" && admin.private && (
            <p>{t("personal_repository_write_access")}</p>
          )}
          <label className="block space-y-2">
            {t("recipient")}
            <Input name="recipient" maxLength={39} />
          </label>
          <div className="flex flex-wrap gap-3">
            <Button
              type="submit"
              name="action"
              value="invite_collaborator"
              variant="outline"
              disabled={busy || !admin || !deviceId}
            >
              {t("planInvite")}
            </Button>
            <Button
              type="submit"
              name="action"
              value="make_public"
              variant="outline"
              disabled={busy || !admin || !deviceId}
            >
              {t("planPublic")}
            </Button>
          </div>
        </form>
        {plan && (
          <div className="max-w-xl space-y-4">
            <p className="font-medium break-all">
              {plan.repository.full_name}
              {plan.recipient ? ` → ${plan.recipient}` : ""}
            </p>
            <p>{t(plan.warning)}</p>
            <p role="status">
              {t(plan.state)}
              {plan.result ? ` · ${t(plan.result)}` : ""}
            </p>
            {plan.error_reason && (
              <p role="alert">
                {t.has(`errors.${plan.error_reason}`) ? t(`errors.${plan.error_reason}`) : t("actionFailed")}
              </p>
            )}
            {plan.action === "invite_collaborator" && plan.state === "applied" && (
              <Button variant="outline" disabled={busy} onClick={() => run(() => githubActionStatus(csrfToken, plan.plan_id), setPlan)}>
                {t("refreshInvitation")}
              </Button>
            )}
            {(plan.state === "planned" || plan.state === "unknown") && (
              <>
                {plan.action === "make_public" && (
                  <label className="block space-y-2">
                    {t("typeName")}
                    <Input
                      value={typedName}
                      onChange={(e) => setTypedName(e.target.value)}
                      autoComplete="off"
                    />
                  </label>
                )}
                <label className="flex min-h-11 items-start gap-3">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  {t("confirmWarning")}
                </label>
                <Button
                  variant="destructive"
                  disabled={
                    busy ||
                    !confirmed ||
                    (plan.action === "make_public" && typedName !== plan.repository.full_name)
                  }
                  onClick={() =>
                    run(
                      () =>
                        githubConfirm(csrfToken, plan.plan_id, {
                          plan_hash: plan.plan_hash,
                          confirmed: true,
                          typed_repository_name: typedName || null,
                          idempotency_key: crypto.randomUUID(),
                        }),
                      setPlan,
                    )
                  }
                >
                  {t("confirmAction")}
                </Button>
                <Button variant="ghost" onClick={() => setPlan(null)}>
                  {t("cancel")}
                </Button>
              </>
            )}
          </div>
        )}
      </section>
      <section className="border-border space-y-4 border-t pt-6">
        <h2 className="text-xl font-medium">{t("promotionTitle")}</h2>
        <p className="text-muted-foreground max-w-prose">{t("promotionHint")}</p>
        <form
          className="max-w-xl space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!deviceId) return;
            const form = new FormData(event.currentTarget);
            run(
              () =>
                visibilityPlan(csrfToken, {
                  object_kind: "component",
                  stable_id: String(form.get("stableId")),
                  version: String(form.get("version")),
                  visibility: "public",
                  device_id: deviceId,
                  idempotency_key: crypto.randomUUID(),
                }),
              (value) => {
                setPromotion(value);
                setPromotionConfirmed(false);
              },
            );
          }}
        >
          <label className="block space-y-2">
            {t("componentId")}
            <Input name="stableId" required maxLength={64} />
          </label>
          <label className="block space-y-2">
            {t("version")}
            <Input name="version" required pattern="[0-9]+\.[0-9]+" />
          </label>
          <Button type="submit" variant="outline" disabled={busy || !deviceId}>
            {t("planPromotion")}
          </Button>
        </form>
        {promotion && (
          <div className="space-y-3">
            <p className="break-all">
              {promotion.stable_id}@{promotion.version}
            </p>
            <p role="status">{t(promotion.state)}</p>
            {promotion.state === "planned" && (
              <>
                <label className="flex min-h-11 items-start gap-3">
                  <input
                    type="checkbox"
                    checked={promotionConfirmed}
                    onChange={(e) => setPromotionConfirmed(e.target.checked)}
                  />
                  {t("confirmPromotionWarning")}
                </label>
                <Button
                  variant="destructive"
                  disabled={busy || !promotionConfirmed}
                  onClick={() =>
                    run(
                      () =>
                        visibilityConfirm(csrfToken, promotion.plan_id, {
                          plan_hash: promotion.plan_hash,
                          confirmed: true,
                          idempotency_key: crypto.randomUUID(),
                        }),
                      setPromotion,
                    )
                  }
                >
                  {t("confirmPromotion")}
                </Button>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
