"use client";

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Badge } from "@/components/atoms/badge";
import { ExactSourceLink } from "@/components/molecules/exact-source-link";
import { useRouter } from "@/lib/i18n/navigation";
import type { CorporateProjectView } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";

type RepositoryPlan = {
  plan_key: string;
  plan_digest: string;
  name: string;
  repository_url: string;
  provider: "github" | "gitlab";
  default_branch: string;
};

export function CorporateProjectRepository({
  project,
  organizationId,
  authorizationRevision,
  csrfToken,
  canManage,
}: {
  project: CorporateProjectView;
  organizationId: string;
  authorizationRevision: number | string;
  csrfToken: string;
  canManage: boolean;
}) {
  const t = useTranslations("projectRepository");
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState("");
  const [plan, setPlan] = useState<RepositoryPlan | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const repositories = project.repositories ?? [];

  function submit() {
    const effect = plan ? plan.plan_digest : url.trim();
    if (retry.current?.effect !== effect) retry.current = { effect, key: crypto.randomUUID() };
    const body = plan
      ? {
          schema_version: 1,
          plan_key: plan.plan_key,
          plan_digest: plan.plan_digest,
          authorization_revision: authorizationRevision,
          idempotency_key: retry.current.key,
        }
      : {
          schema_version: 1,
          repository_url: url.trim(),
          expected_revision: project.revision,
          authorization_revision: authorizationRevision,
          idempotency_key: retry.current.key,
        };
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutation({
        csrfToken,
        organizationId,
        path: `/v1/corporate/organizations/${organizationId}/projects/${project.project_id}/${plan ? "repository" : "repository-plan"}`,
        method: "POST",
        body,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      retry.current = null;
      if (!plan) {
        setPlan(result.data as RepositoryPlan);
        return;
      }
      setEditing(false);
      setPlan(null);
      setUrl("");
      router.refresh();
    });
  }

  return (
    <section
      className="border-border bg-card space-y-4 rounded-lg border p-5"
      aria-label={t("title")}
    >
      <h2 className="text-sm font-medium">{t("title")}</h2>
      {repositories.length ? (
        repositories.map((repository) => (
          <RepositorySource
            key={repository.provider_project_id}
            repository={repository}
            branchLabel={t("branch")}
          />
        ))
      ) : (
        <p className="text-muted-foreground text-sm">{t("empty")}</p>
      )}
      {!repositories.length && canManage && !editing && (
        <Button
          variant="outline"
          className="w-full"
          onClick={() => {
            setEditing(true);
          }}
        >
          <Icon name="link" size="sm" />
          {t("link")}
        </Button>
      )}
      {editing && (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <Label htmlFor={`repository-${project.project_id}`}>{t("url")}</Label>
          <Input
            id={`repository-${project.project_id}`}
            type="url"
            required
            maxLength={512}
            value={url}
            disabled={busy || Boolean(plan)}
            placeholder={t("placeholder")}
            onChange={(event) => {
              setUrl(event.target.value);
              setPlan(null);
              setMessage(null);
            }}
          />
          <p className="text-muted-foreground text-xs">{t("hint")}</p>
          {plan && (
            <div className="space-y-1 text-sm">
              <p className="font-medium">{plan.name}</p>
              <p>
                {plan.provider === "github" ? "GitHub" : "GitLab"} �{" "}
                <span className="font-mono">{plan.default_branch}</span>
              </p>
              <p className="text-muted-foreground">{t("confirmHint")}</p>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={busy || !url.trim()}>
              {busy ? t("working") : plan ? t("confirm") : t("check")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setPlan(null);
                setMessage(null);
              }}
            >
              {t("cancel")}
            </Button>
          </div>
        </form>
      )}
      {message && (
        <p role="alert" className="text-destructive text-sm">
          {message}
        </p>
      )}
    </section>
  );
}

function RepositorySource({
  repository,
  branchLabel,
}: {
  repository: NonNullable<CorporateProjectView["repositories"]>[number];
  branchLabel: string;
}) {
  return (
    <div className="space-y-2 break-all">
      <Badge variant="secondary">{repository.provider === "github" ? "GitHub" : "GitLab"}</Badge>
      <p className="text-sm">
        <ExactSourceLink
          source={null}
          label={repository.namespace}
          links={[
            {
              href: repository.repository_url,
              exact: false,
              provider: repository.provider === "github" ? "GitHub" : "GitLab",
              label: repository.namespace,
            },
          ]}
        />
      </p>
      <p className="text-muted-foreground font-mono text-xs">{repository.repository_url}</p>
      {repository.default_branch && (
        <p className="text-muted-foreground text-sm">
          {branchLabel}: <span className="font-mono">{repository.default_branch}</span>
        </p>
      )}
    </div>
  );
}
