"use client";

import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslations } from "next-intl";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { CorporateDirectoryResults } from "@/components/organisms/corporate-directory-results";
import type {
  DirectoryItem,
  DirectoryResource,
} from "@/components/organisms/corporate-directory-types";
import { useRouter } from "@/lib/i18n/navigation";

type Props = {
  resource: DirectoryResource;
  items: readonly DirectoryItem[];
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  canCreate: boolean;
  roles: string[];
  initialQuery?: string;
  initialStatus?: string;
  showHeader?: boolean;
  customCreate?: ReactNode | undefined;
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
  showHeader = true,
  customCreate,
}: Props) {
  const t = useTranslations("hub");
  const c = useTranslations("corporate");
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const titleKey = resource === "members" ? "employees" : resource;
  const description = {
    projects: t("browseProjects"),
    teams: t("browseTeams"),
    members: t("browseEmployees"),
    technologies: t("browseTechnologies"),
    components: t("browseComponents"),
  }[resource];
  const addLabel = {
    projects: t("addProject"),
    teams: t("addTeam"),
    members: t("addEmployee"),
    technologies: t("addTechnology"),
    components: t("components"),
  }[resource];

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
    <div className="min-w-0 space-y-6">
      {showHeader ? (
        <header className="min-w-0 space-y-2">
          <div className="min-w-0 space-y-2">
            <h1 className="text-4xl font-medium tracking-tight break-words">{t(titleKey)}</h1>
            <p className="text-muted-foreground text-lg">{description}</p>
          </div>
        </header>
      ) : null}
      <CorporateDirectoryResults
        resource={resource}
        items={items}
        initialQuery={initialQuery}
        initialStatus={initialStatus}
        addLabel={showHeader && canCreate ? addLabel : undefined}
        cancelLabel={t("cancel")}
        adding={adding}
        onAdd={
          showHeader && canCreate
            ? () => {
                setAdding((open) => !open);
              }
            : undefined
        }
        filters={new URLSearchParams({
          ...(initialQuery ? { query: initialQuery } : {}),
          ...(initialStatus ? { status: initialStatus } : {}),
        }).toString()}
      />
      {adding && customCreate ? customCreate : null}
      {adding && !customCreate ? (
        <form
          className="border-border bg-card max-w-xl space-y-4 rounded-lg border p-5"
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
            {resource === "teams" ? (
              <div className="space-y-2">
                <Label htmlFor="create-description">{c("description")}</Label>
                <Textarea id="create-description" name="description" maxLength={2000} />
              </div>
            ) : null}
            {resource === "members" ? (
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
            ) : null}
            <Button type="submit">{t("save")}</Button>
          </fieldset>
          {message ? (
            <p role="alert" className="text-sm">
              {message}
            </p>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}
