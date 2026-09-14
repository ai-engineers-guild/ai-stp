"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import {
  CorporateDirectoryResults,
  type DirectoryItem,
} from "@/components/organisms/corporate-directory-results";
import { Textarea } from "@/components/atoms/textarea";
import { useRouter } from "@/lib/i18n/navigation";

type Item = DirectoryItem;
type Props = {
  resource: "projects" | "teams" | "members" | "technologies";
  items: Item[];
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  canCreate: boolean;
  roles: string[];
  initialQuery?: string;
  initialStatus?: string;
};

// eslint-disable-next-line max-lines-per-function
export function CorporateDirectory({
  resource,
  items,
  organizationId,
  authorizationRevision,
  csrfToken,
  canCreate,
  roles,
  initialQuery = "",
  initialStatus = "",
}: Props) {
  const t = useTranslations("hub");
  const c = useTranslations("corporate");
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [status, setStatus] = useState(initialStatus);
  useEffect(() => {
    function restoreFilters() {
      const params = new URLSearchParams(window.location.search);
      setQuery(params.get("query") ?? "");
      setStatus(params.get("status") ?? "");
    }
    window.addEventListener("popstate", restoreFilters);
    return () => {
      window.removeEventListener("popstate", restoreFilters);
    };
  }, []);
  const filters = new URLSearchParams({
    ...(query ? { query } : {}),
    ...(status ? { status } : {}),
  }).toString();
  function updateFilters(nextQuery: string, nextStatus: string) {
    setQuery(nextQuery);
    setStatus(nextStatus);
    const url = new URL(window.location.href);
    if (nextQuery) url.searchParams.set("query", nextQuery);
    else url.searchParams.delete("query");
    if (nextStatus) url.searchParams.set("status", nextStatus);
    else url.searchParams.delete("status");
    window.history.replaceState(window.history.state, "", url);
  }
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const visible = items.filter(
    (item) =>
      item.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()) &&
      (!status || item.state === status),
  );
  async function create(form: HTMLFormElement) {
    const data = new FormData(form);
    const fields =
      resource === "members"
        ? { display_name: data.get("name"), email: data.get("email"), role: data.get("role") }
        : {
            name: data.get("name"),
            ...(resource === "teams" ? { description: data.get("description") } : {}),
          };
    const effect = JSON.stringify(fields);
    if (retry.current?.effect !== effect) retry.current = { effect, key: crypto.randomUUID() };
    setBusy(true);
    setMessage(null);
    try {
      const result = await corporateMutationAction({
        organizationId,
        csrfToken,
        method: "POST",
        path: `/v1/corporate/organizations/${organizationId}/${resource}`,
        body: {
          schema_version: 1,
          authorization_revision: authorizationRevision,
          idempotency_key: retry.current.key,
          ...fields,
        },
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      setAdding(false);
      retry.current = null;
      router.refresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48 flex-1 space-y-2">
          <Label htmlFor="directory-search">{t("search")}</Label>
          <Input
            id="directory-search"
            value={query}
            onChange={(event) => {
              updateFilters(event.target.value, status);
            }}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="directory-status">{t("status")}</Label>
          <select
            id="directory-status"
            value={status}
            onChange={(event) => {
              updateFilters(query, event.target.value);
            }}
            className="border-input bg-background min-h-11 rounded-sm border px-3 text-sm"
          >
            <option value="">{t("all")}</option>
            {[...new Set(items.map((item) => item.state))].map((value) => (
              <option key={value} value={value}>
                {t(value)}
              </option>
            ))}
          </select>
        </div>
        {canCreate && (
          <Button
            disabled={busy}
            onClick={() => {
              setAdding(!adding);
            }}
          >
            {t(adding ? "cancel" : "create")}
          </Button>
        )}
      </div>
      {adding && (
        <form
          className="border-border max-w-xl space-y-4 rounded-lg border p-5"
          onSubmit={(event) => {
            event.preventDefault();
            void create(event.currentTarget);
          }}
        >
          <fieldset disabled={busy} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="create-name">
                {c(resource === "members" ? "displayName" : "name")}
              </Label>
              <Input
                id="create-name"
                name="name"
                required
                maxLength={resource === "members" ? 80 : 200}
              />
            </div>
            {resource === "teams" && (
              <div className="space-y-2">
                <Label htmlFor="create-description">{c("description")}</Label>
                <Textarea id="create-description" name="description" maxLength={2000} />
              </div>
            )}
            {resource === "members" && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="create-email">{c("email")}</Label>
                  <Input id="create-email" name="email" type="email" required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="create-role">{c("organizationRole")}</Label>
                  <select
                    id="create-role"
                    name="role"
                    className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
                  >
                    {roles.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            )}
            <Button type="submit">{t("save")}</Button>
          </fieldset>
          {message && (
            <p role="alert" className="text-sm">
              {message}
            </p>
          )}
        </form>
      )}
      <CorporateDirectoryResults resource={resource} items={visible} filters={filters} />
    </div>
  );
}
