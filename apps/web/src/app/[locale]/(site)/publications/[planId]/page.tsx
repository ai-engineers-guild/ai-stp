import { getTranslations, setRequestLocale } from "next-intl/server";

import { Badge } from "@/components/atoms/badge";
import { ConfirmPublicationForm } from "@/components/organisms/confirm-publication-form";
import { StatePanel } from "@/components/molecules/state-panel";
import { ApiError } from "@/lib/api/errors";
import { readPublicationPlan } from "@/lib/api/publications";
import { readCsrfToken } from "@/lib/auth/session";
import { requireSession, sessionCookieValue } from "@/lib/auth/require-session";

type PageProps = {
  params: Promise<{ locale: string; planId: string }>;
};

export default async function PublicationPlanPage({ params }: PageProps) {
  const { locale, planId } = await params;
  setRequestLocale(locale);
  await requireSession(locale, `/${locale}/publications/${planId}`);
  const t = await getTranslations("publications");
  const tc = await getTranslations("common");
  const token = await sessionCookieValue();
  const csrf = await readCsrfToken();

  let plan;
  try {
    plan = await readPublicationPlan(token ?? "", planId);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 403)) {
      return <StatePanel kind="error" title={tc("notFound")} description={t("notFound")} />;
    }
    if (error instanceof ApiError && error.code === "AI_STP_UNAVAILABLE") {
      return <StatePanel kind="error" title={tc("error")} description={tc("apiUnavailable")} />;
    }
    throw error;
  }

  const canConfirm = plan.state === "ready" && csrf;

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-medium tracking-tight">{t("title")}</h1>
        <p className="text-muted-foreground text-sm">{t("subtitle")}</p>
      </div>

      <dl className="bg-muted/40 border-border space-y-3 rounded-lg border p-4 text-sm">
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("state")}</dt>
          <dd>
            <Badge variant="outline" className="font-mono text-xs">
              {plan.state}
            </Badge>
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("object")}</dt>
          <dd className="font-mono text-xs">
            {plan.object_kind} / {plan.stable_id} / {plan.version}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("digest")}</dt>
          <dd className="font-mono text-xs break-all">{plan.content_digest}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("planHash")}</dt>
          <dd className="font-mono text-xs break-all">{plan.plan_hash}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("policy")}</dt>
          <dd className="font-mono text-xs">{plan.policy_version}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("expires")}</dt>
          <dd className="font-mono text-xs">{plan.expires_at}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground font-mono text-xs">{t("effects")}</dt>
          <dd className="font-mono text-xs">{plan.effects.join(", ") || "—"}</dd>
        </div>
      </dl>

      {plan.evidence.length > 0 ? (
        <ul className="divide-border border-border divide-y rounded-lg border">
          {plan.evidence.map((row) => (
            <li
              key={`${row.check_id}-${row.source}`}
              className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
            >
              <span className="font-mono text-xs">{row.check_id}</span>
              <Badge variant="outline" className="font-mono text-xs">
                {row.result} · {row.source}
              </Badge>
            </li>
          ))}
        </ul>
      ) : null}

      {canConfirm ? (
        <ConfirmPublicationForm
          planId={plan.plan_id}
          planHash={plan.plan_hash}
          csrfToken={csrf}
          labels={{
            confirm: t("confirm"),
            confirming: t("confirming"),
            warning: t("confirmWarning"),
          }}
        />
      ) : (
        <p className="text-muted-foreground text-sm" role="status">
          {t("statusOnly", { state: plan.state })}
        </p>
      )}
    </div>
  );
}
