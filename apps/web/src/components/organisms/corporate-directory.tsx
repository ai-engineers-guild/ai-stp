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
  CorporateCatalogFacet,
  CorporateCatalogFacetConfig,
  DirectoryItem,
  DirectoryResource,
} from "@/components/organisms/corporate-directory-types";
import { useRouter } from "@/lib/i18n/navigation";

const DIRECTORY_DESCRIPTION_KEYS = {
  projects: "browseProjects",
  teams: "browseTeams",
  members: "browseEmployees",
  technologies: "browseTechnologies",
  components: "browseComponents",
} as const;

const DIRECTORY_ADD_KEYS = {
  projects: "addProject",
  teams: "addTeam",
  members: "addEmployee",
  technologies: "addTechnology",
  components: "components",
} as const;

type Props = {
  resource: DirectoryResource;
  items: readonly DirectoryItem[];
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  canCreate: boolean;
  roles: string[];
  initialQuery?: string;
  showHeader?: boolean;
  customCreate?: ReactNode | undefined;
  catalogFacets?: readonly CorporateCatalogFacetConfig[];
  catalogFacetValues?: Partial<Record<CorporateCatalogFacet, string[]>>;
};

export function CorporateDirectory({
  resource,
  items,
  organizationId,
  authorizationRevision,
  csrfToken,
  canCreate,
  roles,
  initialQuery = "",
  showHeader = true,
  customCreate,
  catalogFacets,
  catalogFacetValues,
}: Props) {
  const t = useTranslations("hub");
  const c = useTranslations("corporate");
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const titleKey = resource === "members" ? "employees" : resource;
  const description = t(DIRECTORY_DESCRIPTION_KEYS[resource]);
  const addLabel = t(DIRECTORY_ADD_KEYS[resource]);

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
        {...(catalogFacets ? { catalogFacets } : {})}
        {...(catalogFacetValues ? { initialCatalogSelected: catalogFacetValues } : {})}
        filters={new URLSearchParams({
          ...(initialQuery ? { query: initialQuery } : {}),
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
