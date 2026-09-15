"use client";

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import { corporateMutationAction, corporateTechnologyMergePlanAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { useRouter } from "@/lib/i18n/navigation";
import type {
  TechnologyMergePlanView,
  TechnologyMergeRequest,
  TechnologyView,
} from "@/lib/api/generated/types.gen";

export function TechnologyMergeControls({
  technology,
  organizationId,
  authorizationRevision,
  csrfToken,
}: {
  technology: TechnologyView;
  organizationId: string;
  authorizationRevision: string;
  csrfToken: string;
}) {
  const t = useTranslations("technology");
  const router = useRouter();
  const revision = useRef(technology.revision);
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const [plan, setPlan] = useState<TechnologyMergePlanView | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  function preview(form: HTMLFormElement) {
    const targetId = new FormData(form).get("target_id");
    if (typeof targetId !== "string") return;
    setPlan(null);
    setMessage(null);
    startTransition(async () => {
      const result = await corporateTechnologyMergePlanAction({
        organizationId,
        csrfToken,
        sourceId: technology.technology_id,
        targetId,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      if (result.data.source.revision !== revision.current) {
        setMessage(t("mergeRevisionChanged"));
        return;
      }
      setPlan(result.data);
    });
  }
  function merge() {
    if (!plan) return;
    const effect = {
      target_id: plan.target.technology_id,
      expected_revision: revision.current,
      target_expected_revision: plan.target.revision,
      plan_digest: plan.digest,
    };
    const fingerprint = JSON.stringify(effect);
    if (retry.current?.effect !== fingerprint)
      retry.current = { effect: fingerprint, key: crypto.randomUUID() };
    const body: TechnologyMergeRequest = {
      ...effect,
      schema_version: 1,
      authorization_revision: authorizationRevision,
      idempotency_key: retry.current.key,
    };
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        organizationId,
        csrfToken,
        body,
        method: "POST",
        path: `/v1/corporate/organizations/${organizationId}/technologies/${technology.technology_id}/merge`,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      retry.current = null;
      setMessage(t("saved"));
      router.push(`/corporate/technologies/${plan.target.technology_id}`);
    });
  }
  return (
    <section className="max-w-prose space-y-4" aria-busy={busy}>
      <h2 className="text-xl font-medium">{t("mergeTitle")}</h2>
      <p className="text-muted-foreground text-sm">{t("mergeDescription")}</p>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          preview(event.currentTarget);
        }}
      >
        <Label htmlFor="merge-target">{t("mergeTarget")}</Label>
        <Input
          id="merge-target"
          name="target_id"
          required
          pattern="technology_[0-9A-HJKMNP-TV-Z]{26}"
          disabled={busy}
          onChange={() => {
            setPlan(null);
          }}
        />
        <Button type="submit" size="lg" variant="outline" disabled={busy}>
          {t("mergePreview")}
        </Button>
      </form>
      {plan && (
        <div className="space-y-3" role="status">
          <p>
            {t("mergePlanSummary", {
              source: plan.source.name,
              target: plan.target.name,
              projects: plan.affected_project_count,
              teams: plan.affected_team_count,
            })}
          </p>
          <p className="text-muted-foreground text-sm">{t("mergePlanRetention")}</p>
          <details>
            <summary className="cursor-pointer text-sm">{t("mergeExactPlan")}</summary>
            <code className="block py-2 text-xs break-all">{plan.digest}</code>
          </details>
          <Button type="button" size="lg" disabled={busy} onClick={merge}>
            {t("mergeApply")}
          </Button>
        </div>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
