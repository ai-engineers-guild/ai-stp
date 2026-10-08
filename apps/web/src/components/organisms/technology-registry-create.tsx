"use client";

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import {
  AreaField,
  CategoryStateField,
  TechnologyFields,
} from "@/components/organisms/technology-registry-fields";
import { useRouter } from "@/lib/i18n/navigation";
import type {
  AreaView,
  AreaWriteRequest,
  CategoryView,
  CategoryWriteRequest,
  TechnologyAreaMetadata,
  TechnologyCategoryMetadata,
  TechnologyMetadata,
  TechnologyWriteRequest,
  TechnologySeedRequest,
  TechnologyView,
  TechnologyLifecycleRequest,
} from "@/lib/api/generated/types.gen";

type RegistryKind = "category" | "technology" | "area";

const REGISTRY_ENDPOINTS = {
  area: "technology-areas",
  category: "technology-categories",
  technology: "technologies",
} as const;

const REGISTRY_TITLE_KEYS = {
  create: { area: "areas.create", category: "createCategory", technology: "createTechnology" },
  edit: { area: "areas.edit", category: "editCategory", technology: "editTechnology" },
} as const;

function formText(data: FormData) {
  return (key: string) => {
    const value = data.get(key);
    return typeof value === "string" ? value : "";
  };
}

function registryMetadata(
  kind: RegistryKind,
  data: FormData,
  categories: CategoryView[] | null,
): TechnologyAreaMetadata | TechnologyCategoryMetadata | TechnologyMetadata {
  const text = formText(data);
  const lines = (key: string) =>
    text(key)
      .split("\n")
      .map((value) => value.trim())
      .filter(Boolean);
  if (kind !== "technology") return { name: text("name"), description: text("description") };
  return {
    name: text("name"),
    description: text("description"),
    category_ids:
      categories === null
        ? text("category_ids").split(/\s+/).filter(Boolean)
        : data.getAll("category_ids").filter((value): value is string => typeof value === "string"),
    aliases: lines("aliases"),
    icon_url: text("icon_url") || null,
    official_urls: lines("official_urls"),
  };
}

function registryBody(
  kind: RegistryKind,
  data: FormData,
  options: {
    metadata: TechnologyAreaMetadata | TechnologyCategoryMetadata | TechnologyMetadata;
    areas: AreaView[] | null | undefined;
    record: TechnologyView | CategoryView | AreaView | undefined;
    revision: number;
    authorizationRevision: string;
    idempotencyKey: string;
  },
): AreaWriteRequest | CategoryWriteRequest | TechnologyWriteRequest {
  const requestedState = formText(data)("state");
  return {
    schema_version: 1,
    expected_revision: options.revision,
    authorization_revision: options.authorizationRevision,
    idempotency_key: options.idempotencyKey,
    metadata: options.metadata,
    ...(kind === "category" && options.areas != null
      ? { area_id: formText(data)("area_id") || null }
      : {}),
    ...(kind !== "technology" &&
    !options.record &&
    (requestedState === "draft" || requestedState === "active")
      ? { state: requestedState }
      : {}),
  };
}

export function TechnologyRegistrySeed({
  organizationId,
  authorizationRevision,
  csrfToken,
}: {
  organizationId: string;
  authorizationRevision: string;
  csrfToken: string;
}) {
  const t = useTranslations("technology");
  const router = useRouter();
  const retry = useRef<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  return (
    <section className="max-w-prose space-y-3" aria-busy={busy}>
      <p className="text-muted-foreground text-sm">{t("seedDescription")}</p>
      <Button
        size="lg"
        disabled={busy}
        onClick={() => {
          retry.current ??= crypto.randomUUID();
          const body: TechnologySeedRequest = {
            schema_version: 1,
            seed_version: 1,
            expected_revision: 0,
            authorization_revision: authorizationRevision,
            idempotency_key: retry.current,
          };
          setMessage(null);
          startTransition(async () => {
            const result = await corporateMutationAction({
              csrfToken,
              organizationId,
              method: "POST",
              body,
              path: `/v1/corporate/organizations/${organizationId}/technology-seed`,
            });
            if (!result.ok) {
              setMessage(result.message);
              return;
            }
            retry.current = null;
            setMessage(t("saved"));
            router.refresh();
          });
        }}
      >
        {t(busy ? "saving" : "importSeed")}
      </Button>
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
    </section>
  );
}

export function TechnologyRegistryCreate({
  kind,
  organizationId,
  authorizationRevision,
  csrfToken,
  categories,
  areas,
  initial,
  initialCategory,
  initialArea,
}: {
  kind: RegistryKind;
  organizationId: string;
  authorizationRevision: string;
  csrfToken: string;
  categories: CategoryView[] | null;
  areas?: AreaView[] | null;
  initial?: TechnologyView;
  initialCategory?: CategoryView;
  initialArea?: AreaView;
}) {
  const t = useTranslations("technology");
  const router = useRouter();
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const recordId = initial?.technology_id ?? initialCategory?.category_id ?? initialArea?.area_id;
  const record = initial ?? initialCategory ?? initialArea;
  const prefix = `create-${kind}-${recordId ?? "new"}`;
  const recordRevision = useRef(record?.revision ?? 0);

  function submit(form: HTMLFormElement) {
    const data = new FormData(form);
    const metadata = registryMetadata(kind, data, categories);
    const effect = JSON.stringify(metadata);
    if (retry.current?.effect !== effect) retry.current = { effect, key: crypto.randomUUID() };
    const body = registryBody(kind, data, {
      metadata,
      areas,
      record,
      revision: recordRevision.current,
      authorizationRevision,
      idempotencyKey: retry.current.key,
    });
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        path: `/v1/corporate/organizations/${organizationId}/${REGISTRY_ENDPOINTS[kind]}${recordId ? `/${recordId}` : ""}`,
        method: record ? "PUT" : "POST",
        body,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      retry.current = null;
      if (record) recordRevision.current += 1;
      if (!record) form.reset();
      setMessage(t("saved"));
      router.refresh();
    });
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit(event.currentTarget);
      }}
      className="max-w-prose space-y-4"
      aria-busy={busy}
    >
      <h2 className="text-xl font-medium">
        {t(REGISTRY_TITLE_KEYS[record ? "edit" : "create"][kind])}
      </h2>
      <fieldset disabled={busy} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor={`${prefix}-name`}>{t("name")}</Label>
          <Input
            id={`${prefix}-name`}
            name="name"
            required
            maxLength={200}
            defaultValue={record?.name}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor={`${prefix}-description`}>{t("details")}</Label>
          <Input
            id={`${prefix}-description`}
            name="description"
            maxLength={kind === "category" ? 2000 : 4000}
            defaultValue={record?.description}
          />
        </div>
        {kind === "category" && areas != null && (
          <AreaField prefix={prefix} areas={areas} initial={initialCategory} />
        )}
        {kind !== "technology" && !record && <CategoryStateField prefix={prefix} />}
        {kind === "technology" && (
          <TechnologyFields prefix={prefix} categories={categories} initial={initial} />
        )}
        <Button
          type="submit"
          size="lg"
          disabled={kind === "technology" && categories?.length === 0}
        >
          {t(busy ? "saving" : record ? "saveChanges" : REGISTRY_TITLE_KEYS.create[kind])}
        </Button>
      </fieldset>
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
    </form>
  );
}

export function TechnologyLifecycleControls({
  technology,
  capabilities,
  organizationId,
  authorizationRevision,
  csrfToken,
}: {
  technology: TechnologyView;
  capabilities: string[];
  organizationId: string;
  authorizationRevision: string;
  csrfToken: string;
}) {
  const t = useTranslations("technology");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const retry = useRef<{ target: string; key: string } | null>(null);
  const targets =
    technology.lifecycle === "archived"
      ? [technology.restore_lifecycle]
      : technology.lifecycle === "draft"
        ? (["active", "archived"] as const)
        : technology.lifecycle === "active"
          ? (["deprecated", "archived"] as const)
          : (["active", "archived"] as const);
  const allowed = targets.filter((target) =>
    capabilities.includes(
      target === "active"
        ? "technology.approve"
        : target === "archived"
          ? "technology.delete"
          : "technology.update",
    ),
  );
  if (!allowed.length || technology.redirect_id) return null;
  return (
    <section className="space-y-3" aria-busy={busy}>
      <h2 className="text-xl font-medium">{t("lifecycle")}</h2>
      <p className="text-muted-foreground text-sm">{t("lifecycleDescription")}</p>
      <div className="flex flex-wrap gap-3">
        {allowed.map((target) => (
          <Button
            key={target}
            size="lg"
            disabled={busy}
            onClick={() => {
              const effect = `${technology.revision}:${target}`;
              if (retry.current?.target !== effect)
                retry.current = { target: effect, key: crypto.randomUUID() };
              const body: TechnologyLifecycleRequest = {
                schema_version: 1,
                expected_revision: technology.revision,
                authorization_revision: authorizationRevision,
                idempotency_key: retry.current.key,
                lifecycle: target,
              };
              setMessage(null);
              startTransition(async () => {
                const result = await corporateMutationAction({
                  csrfToken,
                  organizationId,
                  body,
                  method: "PATCH",
                  path: `/v1/corporate/organizations/${organizationId}/technologies/${technology.technology_id}/lifecycle`,
                });
                if (!result.ok) {
                  setMessage(result.message);
                  return;
                }
                retry.current = null;
                setMessage(t("saved"));
                router.refresh();
              });
            }}
          >
            {technology.lifecycle === "archived" ? t("restore") : t(`transition.${target}`)}
          </Button>
        ))}
      </div>
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
    </section>
  );
}
