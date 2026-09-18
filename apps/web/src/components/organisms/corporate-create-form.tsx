"use client";

import { useId, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import {
  corporateCatalogSearchAction,
  corporateCatalogVersionsAction,
  corporateMutationAction,
} from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { useRouter } from "@/lib/i18n/navigation";

type Option = { value: string; label: string };
type CreateResource = "members" | "teams" | "projects";
type CreateOptions = {
  teams: readonly Option[];
  employees: readonly Option[];
  projects: readonly Option[];
  technologies: readonly Option[];
  jobTitles: readonly Option[];
};
type CatalogOption = { id: string; name: string };

function EmployeeCatalogFields({
  formId,
  results,
  selected,
  versions,
  version,
  busy,
  search,
  choose,
  setVersion,
}: {
  formId: string;
  results: CatalogOption[];
  selected: CatalogOption | null;
  versions: string[];
  version: string;
  busy: boolean;
  search: (query: string) => void;
  choose: (item: CatalogOption) => void;
  setVersion: (value: string) => void;
}) {
  const h = useTranslations("hub");
  return (
    <div className="space-y-3 md:col-span-2">
      <Label htmlFor={`${formId}-catalog-query`}>{h("component")}</Label>
      <div className="flex flex-wrap gap-2">
        <Input
          id={`${formId}-catalog-query`}
          name="catalog_query"
          placeholder={h("search")}
          className="min-w-0 flex-1"
        />
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={(event) => {
            const input = event.currentTarget.previousElementSibling as HTMLInputElement;
            search(input.value);
          }}
        >
          {h("search")}
        </Button>
      </div>
      {results.length ? (
        <div className="grid gap-2" role="listbox" aria-label={h("component")}>
          {results.map((item) => (
            <Button
              key={item.id}
              type="button"
              variant={selected?.id === item.id ? "default" : "outline"}
              className="justify-start"
              onClick={() => {
                choose(item);
              }}
            >
              {item.name}
            </Button>
          ))}
        </div>
      ) : null}
      {selected ? (
        <div className="space-y-2">
          <p className="text-muted-foreground text-sm">{selected.name}</p>
          <select
            aria-label={h("exactVersion")}
            value={version}
            disabled={busy}
            onChange={(event) => {
              setVersion(event.target.value);
            }}
            className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
          >
            <option value="">{h("exactVersion")}</option>
            {versions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
      ) : null}
    </div>
  );
}

function CorporateCreateFields({
  resource,
  formId,
  roles,
  options,
  values,
  choose,
  catalogResults,
  catalogSelected,
  catalogVersions,
  catalogVersion,
  catalogBusy,
  searchCatalog,
  chooseCatalog,
  setCatalogVersion,
}: {
  resource: CreateResource;
  formId: string;
  roles: readonly string[];
  options: CreateOptions;
  values: (name: string) => string[];
  choose: (name: string, values: string[]) => void;
  catalogResults: CatalogOption[];
  catalogSelected: CatalogOption | null;
  catalogVersions: string[];
  catalogVersion: string;
  catalogBusy: boolean;
  searchCatalog: (query: string) => void;
  chooseCatalog: (item: CatalogOption) => void;
  setCatalogVersion: (version: string) => void;
}) {
  const c = useTranslations("corporate");
  const h = useTranslations("hub");
  const select = (name: string, label: string, valuesFor: readonly Option[], multiple = true) => (
    <div className="space-y-2">
      <Label>{label}</Label>
      <SearchableMultiSelect
        name={name}
        form={formId}
        label={label}
        searchLabel={`${h("search")}: ${label}`}
        options={valuesFor}
        selected={values(name)}
        multiple={multiple}
        modal
        closeLabel={c("close")}
        onChange={(next) => {
          choose(name, next);
        }}
      />
    </div>
  );

  return (
    <div className="grid gap-5 md:grid-cols-2">
      <div className="space-y-2 md:col-span-2">
        <Label htmlFor={`${formId}-name`}>
          {c(resource === "members" ? "displayName" : "name")}
        </Label>
        <Input
          id={`${formId}-name`}
          name={resource === "members" ? "display_name" : "name"}
          required
          maxLength={resource === "members" ? 80 : 200}
        />
      </div>
      {resource !== "members" ? (
        <div className="space-y-2 md:col-span-2">
          <Label htmlFor={`${formId}-description`}>{c("description")}</Label>
          <Textarea id={`${formId}-description`} name="description" maxLength={2000} />
        </div>
      ) : null}
      {resource === "members" ? (
        <>
          <div className="space-y-2">
            <Label htmlFor={`${formId}-email`}>{c("email")}</Label>
            <Input id={`${formId}-email`} name="email" type="email" required />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${formId}-role`}>{c("role")}</Label>
            <select
              id={`${formId}-role`}
              name="role"
              required
              className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
            >
              {roles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </div>
          {select("team_ids", h("teams"), options.teams)}
          {select("project_ids", h("projects"), options.projects)}
          {select("job_title_ids", h("job_titles"), options.jobTitles, false)}
          <EmployeeCatalogFields
            formId={formId}
            results={catalogResults}
            selected={catalogSelected}
            versions={catalogVersions}
            version={catalogVersion}
            busy={catalogBusy}
            search={searchCatalog}
            choose={chooseCatalog}
            setVersion={setCatalogVersion}
          />
        </>
      ) : null}
      {resource === "teams" ? (
        <>
          {select("employee_ids", h("employees"), options.employees)}
          {select("lead_account_id", h("teamLeads"), options.employees, false)}
          {select("project_ids", h("projects"), options.projects)}
          {select("technology_ids", h("technologies"), options.technologies)}
        </>
      ) : null}
      {resource === "projects" ? (
        <>
          {select("owner_team_id", h("owner"), options.teams, false)}
          {select("technology_ids", h("technologies"), options.technologies)}
        </>
      ) : null}
    </div>
  );
}

// eslint-disable-next-line max-lines-per-function
export function CorporateCreateForm({
  resource,
  organizationId,
  authorizationRevision,
  csrfToken,
  roles,
  teams,
  employees,
  projects,
  technologies,
  jobTitles,
}: {
  resource: CreateResource;
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  roles: readonly string[];
  teams: readonly Option[];
  employees: readonly Option[];
  projects: readonly Option[];
  technologies: readonly Option[];
  jobTitles: readonly Option[];
}) {
  const c = useTranslations("corporate");
  const router = useRouter();
  const formId = useId();
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [catalogResults, setCatalogResults] = useState<CatalogOption[]>([]);
  const [catalogSelected, setCatalogSelected] = useState<CatalogOption | null>(null);
  const [catalogVersions, setCatalogVersions] = useState<string[]>([]);
  const [catalogVersion, setCatalogVersion] = useState("");
  const [catalogBusy, setCatalogBusy] = useState(false);
  const retry = useRef<{ effect: string; key: string } | null>(null);

  const choose = (name: string, values: string[]) => {
    setSelected((current) => ({ ...current, [name]: values }));
  };
  const values = (name: string) => selected[name] ?? [];
  const target = resource === "members" ? "employees" : resource;

  async function searchCatalog(query: string) {
    if (!query.trim()) return;
    setCatalogBusy(true);
    setCatalogSelected(null);
    setCatalogVersions([]);
    setCatalogVersion("");
    const result = await corporateCatalogSearchAction({
      kind: "component",
      query: query.trim(),
      csrfToken,
    });
    if (result.ok) setCatalogResults(result.items);
    else setMessage(result.message);
    setCatalogBusy(false);
  }

  async function chooseCatalog(item: CatalogOption) {
    setCatalogBusy(true);
    setCatalogSelected(item);
    setCatalogVersions([]);
    setCatalogVersion("");
    const result = await corporateCatalogVersionsAction({
      kind: "component",
      id: item.id,
      csrfToken,
    });
    if (result.ok) {
      setCatalogVersions(result.versions);
      setCatalogVersion(result.versions[0] ?? "");
    } else setMessage(result.message);
    setCatalogBusy(false);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body =
      resource === "members"
        ? {
            display_name: form.get("display_name"),
            email: form.get("email"),
            role: form.get("role"),
            team_ids: values("team_ids"),
            project_ids: values("project_ids"),
            job_title_id: values("job_title_ids")[0] ?? null,
            catalog_assignments:
              catalogSelected && catalogVersion
                ? [
                    {
                      object_kind: "component",
                      stable_id: catalogSelected.id,
                      version: catalogVersion,
                    },
                  ]
                : [],
          }
        : resource === "teams"
          ? {
              name: form.get("name"),
              description: form.get("description"),
              employee_ids: values("employee_ids"),
              lead_account_id: values("lead_account_id")[0] ?? null,
              project_ids: values("project_ids"),
              technology_ids: values("technology_ids"),
            }
          : {
              name: form.get("name"),
              description: form.get("description"),
              owner_team_id: values("owner_team_id")[0] ?? null,
              technology_ids: values("technology_ids"),
            };
    const effect = JSON.stringify(body);
    if (retry.current?.effect !== effect) retry.current = { effect, key: crypto.randomUUID() };
    setBusy(true);
    setMessage(null);
    const result = await corporateMutationAction({
      organizationId,
      csrfToken,
      method: "POST",
      path: `/v1/corporate/organizations/${organizationId}/${resource}`,
      body: {
        schema_version: 1,
        authorization_revision: authorizationRevision,
        idempotency_key: retry.current.key,
        ...body,
      },
    });
    setBusy(false);
    if (!result.ok) {
      setMessage(result.message);
      return;
    }
    retry.current = null;
    router.push(`/corporate/${target}`);
  }

  const options: CreateOptions = {
    teams,
    employees,
    projects,
    technologies,
    jobTitles,
  };
  return (
    <form
      id={formId}
      onSubmit={(event) => {
        void submit(event);
      }}
      className="bg-card border-border max-w-3xl space-y-6 rounded-lg border p-5"
    >
      <CorporateCreateFields
        resource={resource}
        formId={formId}
        roles={roles}
        options={options}
        values={values}
        choose={choose}
        catalogResults={catalogResults}
        catalogSelected={catalogSelected}
        catalogVersions={catalogVersions}
        catalogVersion={catalogVersion}
        catalogBusy={catalogBusy}
        searchCatalog={(query) => {
          void searchCatalog(query);
        }}
        chooseCatalog={(item) => {
          void chooseCatalog(item);
        }}
        setCatalogVersion={setCatalogVersion}
      />
      {message ? (
        <p role="alert" className="text-destructive text-sm">
          {message}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? c("creating") : c("create")}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            router.push(`/corporate/${target}`);
          }}
        >
          {c("cancel")}
        </Button>
      </div>
    </form>
  );
}
