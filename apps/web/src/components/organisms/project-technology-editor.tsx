"use client";
import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { useRouter } from "@/lib/i18n/navigation";
import type {
  ProjectTechnologyView,
  ProjectTechnologyWriteRequest,
} from "@/lib/api/generated/types.gen";

export function ProjectTechnologyEditor({
  organizationId,
  projectId,
  authorizationRevision,
  csrfToken,
  capabilities,
  usages = [],
  technologies = [],
}: {
  organizationId: string;
  projectId: string;
  authorizationRevision: string;
  csrfToken: string;
  capabilities: string[];
  usages?: ProjectTechnologyView[];
  technologies?: { technology_id: string; name: string }[];
}) {
  const t = useTranslations("technology");
  const h = useTranslations("hub");
  const router = useRouter();
  const [technologyId, setTechnologyId] = useState("");
  const [context, setContext] =
    useState<ProjectTechnologyWriteRequest["fact"]["context"]>("production");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const usage = usages.find((item) => item.technology_id === technologyId);
  const fact = usage?.facts.find((item) => item.context === context);
  function submit(form: HTMLFormElement, removing = false) {
    if (!technologyId) return;
    if (
      !capabilities.includes(
        `project_technology.${removing ? "delete" : usage ? "update" : "create"}`,
      )
    ) {
      setMessage(t("notPermitted"));
      return;
    }
    const value = new FormData(form).get("version");
    const version = typeof value === "string" ? value.trim() : "";
    const effect = {
      technology_id: technologyId,
      expected_revision: usage?.revision ?? 0,
      review: "confirmed",
      state: removing ? "retired" : "current",
      fact: {
        context,
        version_kind: version
          ? version === fact?.version
            ? fact.version_kind
            : "declared_range"
          : "unknown",
        version: version || null,
        evidence: fact?.evidence ?? [],
      },
    } satisfies Omit<
      ProjectTechnologyWriteRequest,
      "schema_version" | "authorization_revision" | "idempotency_key"
    >;
    const fingerprint = JSON.stringify(effect);
    if (retry.current?.effect !== fingerprint)
      retry.current = { effect: fingerprint, key: crypto.randomUUID() };
    const body: ProjectTechnologyWriteRequest = {
      ...effect,
      schema_version: 1,
      authorization_revision: authorizationRevision,
      idempotency_key: retry.current.key,
    };
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        method: "PUT",
        body,
        path: `/v1/corporate/organizations/${organizationId}/projects/${projectId}/technologies`,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      retry.current = null;
      setMessage(t("saved"));
      router.refresh();
    });
  }
  return (
    <form
      className="max-w-xl space-y-4"
      aria-busy={busy}
      onSubmit={(event) => {
        event.preventDefault();
        submit(event.currentTarget);
      }}
    >
      <h2 className="text-xl font-medium">{h("technologies")}</h2>
      <fieldset disabled={busy} className="space-y-4">
        <SearchableMultiSelect
          name="technology_id"
          label={h("technologies")}
          searchLabel={h("search")}
          options={technologies.map((item) => ({ value: item.technology_id, label: item.name }))}
          selected={technologyId ? [technologyId] : []}
          multiple={false}
          closeLabel={h("cancel")}
          emptyHint={h("search")}
          onChange={(values) => {
            setTechnologyId(values[0] ?? "");
            setMessage(null);
          }}
        />
        <UsageContextField
          value={context}
          onChange={(value) => {
            setContext(value);
            setMessage(null);
          }}
        />
        <div className="space-y-2">
          <Label htmlFor="usage-version">{t("version")}</Label>
          <Input
            key={`${technologyId}/${context}`}
            id="usage-version"
            name="version"
            maxLength={128}
            defaultValue={fact?.version ?? ""}
          />
        </div>
        <Button
          type="submit"
          disabled={
            !technologyId ||
            !capabilities.includes(`project_technology.${usage ? "update" : "create"}`)
          }
        >
          {t(busy ? "saving" : "saveUsage")}
        </Button>
        {usage?.state === "current" && capabilities.includes("project_technology.delete") && (
          <Button
            type="button"
            variant="outline"
            onClick={(event) => {
              const form = event.currentTarget.form;
              if (form) submit(form, true);
            }}
          >
            {h("unlink")}
          </Button>
        )}
      </fieldset>
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
    </form>
  );
}

function UsageContextField({
  value,
  onChange,
}: {
  value: ProjectTechnologyWriteRequest["fact"]["context"];
  onChange: (value: ProjectTechnologyWriteRequest["fact"]["context"]) => void;
}) {
  const t = useTranslations("technology");
  return (
    <div className="space-y-2">
      <Label htmlFor="usage-context">{t("context")}</Label>
      <select
        id="usage-context"
        className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
        value={value}
        onChange={(event) => {
          const next = event.target.value;
          if (
            next === "production" ||
            next === "development" ||
            next === "testing" ||
            next === "browser_support"
          )
            onChange(next);
        }}
      >
        {(["production", "development", "testing", "browser_support"] as const).map((context) => (
          <option key={context} value={context}>
            {t(`values.${context}`)}
          </option>
        ))}
      </select>
    </div>
  );
}
