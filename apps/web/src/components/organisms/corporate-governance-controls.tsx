"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { useRouter } from "@/lib/i18n/navigation";
import type {
  CategoryView,
  CorporateProjectLifecycleRequest,
  CorporateProjectView,
  ProjectActivityRequest,
  ProjectActivityView,
  TechnologyLandscapePolicyRequest,
  TechnologyLandscapePolicyView,
} from "@/lib/api/generated/types.gen";

export type GovernanceAuthority = {
  organizationId: string;
  authorizationRevision: string;
  csrfToken: string;
};
type Authority = GovernanceAuthority;

export function useGovernanceMutation(authority: GovernanceAuthority) {
  const t = useTranslations("technology");
  const router = useRouter();
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  function save(
    path: string,
    effect: object,
    method: "PUT" | "POST" | "DELETE",
    acknowledged: () => void,
  ) {
    const fingerprint = JSON.stringify({ path, effect, method });
    if (retry.current?.effect !== fingerprint)
      retry.current = { effect: fingerprint, key: crypto.randomUUID() };
    const body = {
      ...effect,
      schema_version: 1,
      authorization_revision: authority.authorizationRevision,
      idempotency_key: retry.current.key,
    };
    setMessage(null);
    setBusy(true);
    void (async () => {
      try {
        const result = await corporateMutationAction({ ...authority, path, method, body });
        if (!result.ok) {
          setMessage(result.message);
          return;
        }
        retry.current = null;
        acknowledged();
        setMessage(t("saved"));
        router.refresh();
      } catch {
        setMessage(t("unavailable"));
      } finally {
        setBusy(false);
      }
    })();
  }
  return { busy, message, save };
}

export function CategoryLifecycleControls({
  category,
  canRemove,
  canRestore,
  ...authority
}: Authority & {
  category: CategoryView;
  canRemove: boolean;
  canRestore: boolean;
}) {
  const t = useTranslations("technology");
  const revision = useRef(category.revision);
  const [state, setState] = useState(category.state);
  const mutation = useGovernanceMutation(authority);
  const restore = state === "archived";
  if (!state || (restore ? !canRestore : !canRemove)) return null;
  return (
    <div className="mt-3 space-y-2" aria-busy={mutation.busy}>
      <Button
        size="lg"
        variant="outline"
        disabled={mutation.busy}
        onClick={() => {
          const path = `/v1/corporate/organizations/${authority.organizationId}/technology-categories/${category.category_id}`;
          mutation.save(
            restore ? `${path}/lifecycle` : path,
            { expected_revision: revision.current, ...(restore ? { target: "active" } : {}) },
            restore ? "POST" : "DELETE",
            () => {
              revision.current += 1;
              setState(restore ? "active" : "archived");
            },
          );
        }}
      >
        {t(mutation.busy ? "saving" : restore ? "restore" : "transition.archived")}
      </Button>
      {mutation.message && <p role="status">{mutation.message}</p>}
    </div>
  );
}

export function TechnologyActivityPolicy({
  policy,
  ...authority
}: Authority & {
  policy: TechnologyLandscapePolicyView;
}) {
  const t = useTranslations("technology");
  const revision = useRef(policy.revision);
  const mutation = useGovernanceMutation(authority);
  return (
    <form
      className="max-w-prose space-y-4"
      aria-busy={mutation.busy}
      onSubmit={(event) => {
        event.preventDefault();
        const months = Number(new FormData(event.currentTarget).get("inactivity_months"));
        if (!Number.isSafeInteger(months) || months < 1 || months > 120) return;
        const effect = {
          inactivity_months: months,
          expected_revision: revision.current,
        } satisfies Omit<
          TechnologyLandscapePolicyRequest,
          "schema_version" | "authorization_revision" | "idempotency_key"
        >;
        mutation.save(
          `/v1/corporate/organizations/${authority.organizationId}/technology-landscape-policy`,
          effect,
          "PUT",
          () => {
            revision.current += 1;
          },
        );
      }}
    >
      <h2 className="text-xl font-medium">{t("activityPolicy")}</h2>
      <p className="text-muted-foreground text-sm">{t("activityPolicyDescription")}</p>
      <Label htmlFor="policy-months">{t("inactivityMonths")}</Label>
      <Input
        id="policy-months"
        name="inactivity_months"
        type="number"
        min={1}
        max={120}
        required
        defaultValue={policy.inactivity_months}
        disabled={mutation.busy}
      />
      <Button type="submit" size="lg" disabled={mutation.busy}>
        {t(mutation.busy ? "saving" : "saveChanges")}
      </Button>
      {mutation.message && <p role="status">{mutation.message}</p>}
    </form>
  );
}

export function ProjectActivityEditor({
  activity,
  ...authority
}: Authority & {
  activity: ProjectActivityView;
}) {
  const t = useTranslations("technology");
  const revision = useRef(activity.revision);
  const mutation = useGovernanceMutation(authority);
  return (
    <form
      className="max-w-prose space-y-4"
      aria-busy={mutation.busy}
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const rawTime = data.get("repository_activity_at");
        const rawOverride = data.get("activity_override");
        const sourceAvailability = data.get("source_availability");
        if (
          sourceAvailability !== "unknown" &&
          sourceAvailability !== "available" &&
          sourceAvailability !== "unavailable"
        )
          return;
        if (typeof rawTime !== "string" || typeof rawOverride !== "string") return;
        const override =
          rawOverride === ""
            ? null
            : rawOverride === "active"
              ? "active"
              : rawOverride === "inactive"
                ? "inactive"
                : undefined;
        if (override === undefined) return;
        const time = rawTime ? new Date(`${rawTime}Z`) : null;
        if (time && !Number.isFinite(time.getTime())) return;
        const effect = {
          repository_activity_at: time?.toISOString() ?? null,
          activity_override: override,
          source_availability: sourceAvailability,
          expected_revision: revision.current,
        } satisfies Omit<
          ProjectActivityRequest,
          "schema_version" | "authorization_revision" | "idempotency_key"
        >;
        mutation.save(
          `/v1/corporate/organizations/${authority.organizationId}/projects/${activity.project_id}/activity`,
          effect,
          "PUT",
          () => {
            revision.current += 1;
          },
        );
      }}
    >
      <h2 className="text-xl font-medium">{t("projectActivity")}</h2>
      <p className="text-muted-foreground text-sm">{t("activityOverrideDescription")}</p>
      <fieldset disabled={mutation.busy} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="project-source-availability">{t("source_availability")}</Label>
          <select
            id="project-source-availability"
            name="source_availability"
            defaultValue={activity.source_availability ?? "unknown"}
            className="border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2"
          >
            {["unknown", "available", "unavailable"].map((value) => (
              <option key={value} value={value}>
                {t(`values.${value}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="project-activity-time">{t("activityTime")}</Label>
          <Input
            id="project-activity-time"
            name="repository_activity_at"
            type="datetime-local"
            step={1}
            defaultValue={activity.repository_activity_at?.slice(0, 19) ?? ""}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="project-activity-override">{t("activityOverride")}</Label>
          <select
            id="project-activity-override"
            name="activity_override"
            defaultValue={activity.activity_override ?? ""}
            className="border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2"
          >
            <option value="">{t("clearOverride")}</option>
            <option value="active">{t("values.active")}</option>
            <option value="inactive">{t("values.inactive")}</option>
          </select>
        </div>
      </fieldset>
      <Button type="submit" size="lg" disabled={mutation.busy}>
        {t(mutation.busy ? "saving" : "saveChanges")}
      </Button>
      {mutation.message && <p role="status">{mutation.message}</p>}
    </form>
  );
}

export function ProjectLifecycleControls({
  project,
  ...authority
}: Authority & {
  project: CorporateProjectView;
}) {
  const t = useTranslations("technology");
  const revision = useRef(project.revision);
  const mutation = useGovernanceMutation(authority);
  const targets =
    project.lifecycle === "active"
      ? (["deprecated", "archived"] as const)
      : project.lifecycle === "deprecated"
        ? (["active", "archived"] as const)
        : project.lifecycle === "archived" || project.lifecycle === "deleted"
          ? (["restore"] as const)
          : [];
  return (
    <section className="max-w-prose space-y-4" aria-busy={mutation.busy}>
      <h2 className="text-xl font-medium">{t("project_lifecycle")}</h2>
      <p className="text-muted-foreground text-sm">{t("projectLifecycleDescription")}</p>
      <div className="flex flex-wrap gap-3">
        {targets.map((target) => (
          <Button
            key={target}
            size="lg"
            variant="outline"
            disabled={mutation.busy}
            onClick={() => {
              const effect = { target, expected_revision: revision.current } satisfies Omit<
                CorporateProjectLifecycleRequest,
                "schema_version" | "authorization_revision" | "idempotency_key"
              >;
              mutation.save(
                `/v1/corporate/organizations/${authority.organizationId}/projects/${project.project_id}/lifecycle`,
                effect,
                "POST",
                () => {
                  revision.current += 1;
                },
              );
            }}
          >
            {target === "restore" ? t("restore") : t(`projectTransition.${target}`)}
          </Button>
        ))}
      </div>
      {mutation.message && <p role="status">{mutation.message}</p>}
    </section>
  );
}
