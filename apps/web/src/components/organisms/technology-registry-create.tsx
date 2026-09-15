"use client";

import { useRef, useState, useTransition } from "react";
import { useTranslations } from "next-intl";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { useRouter } from "@/lib/i18n/navigation";
import type {
  CategoryView,
  CategoryWriteRequest,
  TechnologyWriteRequest,
  TechnologySeedRequest,
  TechnologyView,
  TechnologyLifecycleRequest,
} from "@/lib/api/generated/types.gen";

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
  initial,
  initialCategory,
}: {
  kind: "category" | "technology";
  organizationId: string;
  authorizationRevision: string;
  csrfToken: string;
  categories: CategoryView[] | null;
  initial?: TechnologyView;
  initialCategory?: CategoryView;
}) {
  const t = useTranslations("technology");
  const router = useRouter();
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const recordId = initial?.technology_id ?? initialCategory?.category_id;
  const record = initial ?? initialCategory;
  const prefix = `create-${kind}-${recordId ?? "new"}`;
  const recordRevision = useRef(record?.revision ?? 0);

  function submit(form: HTMLFormElement) {
    const data = new FormData(form);
    const text = (key: string) => {
      const value = data.get(key);
      return typeof value === "string" ? value : "";
    };
    const metadata = {
      name: text("name"),
      description: text("description"),
      ...(kind === "technology"
        ? {
            category_ids:
              categories === null
                ? text("category_ids").split(/\s+/).filter(Boolean)
                : data
                    .getAll("category_ids")
                    .filter((value): value is string => typeof value === "string"),
            aliases: text("aliases")
              .split("\n")
              .map((value) => value.trim())
              .filter(Boolean),
            icon_url: text("icon_url") || null,
            official_urls: text("official_urls")
              .split("\n")
              .map((value) => value.trim())
              .filter(Boolean),
          }
        : {}),
    };
    const effect = JSON.stringify(metadata);
    if (retry.current?.effect !== effect) retry.current = { effect, key: crypto.randomUUID() };
    const body: CategoryWriteRequest | TechnologyWriteRequest = {
      schema_version: 1,
      expected_revision: recordRevision.current,
      authorization_revision: authorizationRevision,
      idempotency_key: retry.current.key,
      metadata,
    };
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        path: `/v1/corporate/organizations/${organizationId}/${kind === "category" ? "technology-categories" : "technologies"}${recordId ? `/${recordId}` : ""}`,
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
        {t(
          record
            ? kind === "category"
              ? "editCategory"
              : "editTechnology"
            : kind === "category"
              ? "createCategory"
              : "createTechnology",
        )}
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
        {kind === "technology" && (
          <TechnologyFields prefix={prefix} categories={categories} initial={initial} />
        )}
        <Button
          type="submit"
          size="lg"
          disabled={kind === "technology" && categories?.length === 0}
        >
          {t(
            busy
              ? "saving"
              : record
                ? "saveChanges"
                : kind === "category"
                  ? "createCategory"
                  : "createTechnology",
          )}
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

function TechnologyFields({
  prefix,
  categories,
  initial,
}: {
  prefix: string;
  categories: CategoryView[] | null;
  initial: TechnologyView | undefined;
}) {
  const t = useTranslations("technology");
  return (
    <>
      {categories === null ? (
        <div className="space-y-2">
          <Label htmlFor={`${prefix}-categories`}>{t("knownCategories")}</Label>
          <Input
            id={`${prefix}-categories`}
            name="category_ids"
            required
            defaultValue={initial?.category_ids.join(" ")}
          />
        </div>
      ) : (
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">{t("categories")}</legend>
          {categories.map((category) => (
            <label key={category.category_id} className="flex min-h-11 items-center gap-3">
              <input
                type="checkbox"
                name="category_ids"
                value={category.category_id}
                defaultChecked={initial?.category_ids.includes(category.category_id)}
                className="accent-primary h-4 w-4"
              />
              {category.name}
            </label>
          ))}
          {categories.length === 0 && (
            <p className="text-muted-foreground text-sm">{t("categoryRequired")}</p>
          )}
        </fieldset>
      )}
      <div className="space-y-2">
        <Label htmlFor={`${prefix}-aliases`}>{t("aliases")}</Label>
        <textarea
          id={`${prefix}-aliases`}
          name="aliases"
          rows={3}
          defaultValue={initial?.aliases.join("\n")}
          className="border-input bg-background focus-visible:ring-ring w-full rounded-sm border px-3 py-2 text-sm focus-visible:ring-2"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor={`${prefix}-icon`}>{t("iconUrl")}</Label>
        <Input
          id={`${prefix}-icon`}
          name="icon_url"
          type="url"
          maxLength={2048}
          defaultValue={initial?.icon_url ?? ""}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor={`${prefix}-official`}>{t("officialUrls")}</Label>
        <textarea
          id={`${prefix}-official`}
          name="official_urls"
          rows={3}
          defaultValue={initial?.official_urls.join("\n")}
          className="border-input bg-background focus-visible:ring-ring w-full rounded-sm border px-3 py-2 text-sm focus-visible:ring-2"
        />
      </div>
    </>
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
