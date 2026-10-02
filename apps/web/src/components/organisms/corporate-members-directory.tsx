"use client";

import { useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/atoms/dialog";
import { CatalogChoiceMenu } from "@/components/molecules/catalog-choice-menu";
import { CorporateCreateForm } from "@/components/organisms/corporate-create-form";
import {
  PEOPLE_PAGE_SIZE,
  PeoplePager,
  PeopleSearch,
  PeopleSelect,
  usePeopleFilters,
  CorporateDetailDrawer,
} from "@/components/organisms/corporate-people-ui";
import type {
  CorporateContext,
  CorporateJobTitleView,
  CorporateMember,
  CorporateRoleView,
  CorporateBinding,
} from "@/lib/api/generated/types.gen";
import { downloadPeopleCsv } from "@/lib/member-export";
import { CorporateMembersTable } from "@/components/organisms/corporate-members-table";
import { Icon } from "@/theme";
import { useRouter, usePathname } from "@/lib/i18n/navigation";
import { roleTitle } from "@/lib/corporate-permission-ui";

type Props = {
  members: readonly CorporateMember[];
  context: CorporateContext;
  roles: readonly CorporateRoleView[];
  jobTitles: readonly CorporateJobTitleView[];
  csrfToken: string;
  now: string;
  accessView?: boolean;
  accessPanel?: ReactNode;
  bindings?: readonly CorporateBinding[];
};

export function selectPeopleMembers(
  members: readonly CorporateMember[],
  context: CorporateContext,
  filters: { query: string; team: string; role: string; status: string; sort: string },
  bindings: readonly CorporateBinding[] = [],
) {
  const query = filters.query.trim().toLowerCase();
  const result = members.filter(
    (member) =>
      (!query ||
        [member.display_name, member.contact_email, member.job_title_name, member.role].some(
          (value) => value?.toLowerCase().includes(query),
        )) &&
      (!filters.role ||
        member.role === filters.role ||
        bindings.some(
          (binding) =>
            binding.account_id === member.account_id &&
            binding.role === filters.role &&
            binding.state === "active",
        )) &&
      (!filters.status || member.state === filters.status) &&
      (!filters.team ||
        context.teams.some(
          (team) =>
            team.team_id === filters.team &&
            team.members.some((entry) => entry.account_id === member.account_id),
        )),
  );
  return result.sort((a, b) => {
    if (filters.sort.startsWith("name"))
      return (
        (a.display_name ?? a.account_id).localeCompare(b.display_name ?? b.account_id) *
        (filters.sort === "name_desc" ? -1 : 1)
      );
    return (
      (a.joined_at ?? "").localeCompare(b.joined_at ?? "") * (filters.sort === "joined" ? 1 : -1) ||
      (a.display_name ?? a.account_id).localeCompare(b.display_name ?? b.account_id)
    );
  });
}

function AddMemberDialog({ context, roles, jobTitles, csrfToken }: Omit<Props, "members" | "now">) {
  const t = useTranslations("people");
  if (!context.capabilities.includes("member.create")) return null;
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" className="h-11">
          <Icon name="plus" size="sm" />
          {t("addMember")}
        </Button>
      </DialogTrigger>
      <DialogContent
        closeLabel={t("close")}
        className="max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto"
      >
        <DialogTitle>{t("addMember")}</DialogTitle>
        <DialogDescription>{t("addMemberBody")}</DialogDescription>
        <CorporateCreateForm
          resource="members"
          organizationId={context.organization.organization_id}
          authorizationRevision={context.organization.authorization_revision}
          csrfToken={csrfToken}
          roles={roles.map((role) => role.name)}
          teams={context.teams.map((team) => ({ value: team.team_id, label: team.name }))}
          employees={[]}
          projects={context.projects.map((project) => ({
            value: project.project_id,
            label: project.name,
          }))}
          technologies={[]}
          jobTitles={jobTitles.map((title) => ({ value: title.job_title_id, label: title.name }))}
        />
      </DialogContent>
    </Dialog>
  );
}

/** This administration table extends the directory kit with membership-specific columns and selection. */
export function CorporateMembersDirectory(props: Props) {
  const { members, context, now } = props;
  const t = useTranslations("people");
  const a = useTranslations("accessUi");
  const inspect = useEmployeeSelection();
  const filters = usePeopleFilters();
  const activeMember = members.find((member) => member.account_id === filters.get("employee"));
  const [selected, setSelected] = useState<string[]>([]);
  const sort = filters.get("sort") || "joined_desc";
  const filtered = selectPeopleMembers(
    members,
    context,
    {
      query: filters.get("query"),
      team: filters.get("team"),
      role: filters.get("role"),
      status: filters.get("status"),
      sort,
    },
    props.accessView ? props.bindings : [],
  );
  const page = Math.min(
    Math.max(1, Number(filters.get("page")) || 1),
    Math.max(1, Math.ceil(filtered.length / PEOPLE_PAGE_SIZE)),
  );
  const rows = filtered.slice((page - 1) * PEOPLE_PAGE_SIZE, page * PEOPLE_PAGE_SIZE);
  const chosen = filtered.filter((member) => selected.includes(member.account_id));
  const exportRows = () => {
    exportMembers(chosen.length ? chosen : filtered, context);
  };

  return (
    <section
      aria-label={props.accessView ? a("employeeAccess") : t("members")}
      className={`min-w-0 space-y-4 ${props.accessView && activeMember ? "2xl:pr-[27rem]" : ""}`}
      data-ui={props.accessView ? "employee-access-directory" : "members-directory"}
    >
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 basis-full xl:flex-1">
          <PeopleSearch
            label={props.accessView ? a("searchEmployees") : t("searchMembers")}
            value={filters.get("query")}
            onChange={(value) => {
              filters.update("query", value);
            }}
          />
        </div>
        <PeopleSelect
          label={t("allTeams")}
          value={filters.get("team")}
          onChange={(value) => {
            filters.update("team", value);
          }}
          options={context.teams.map((team) => ({ value: team.team_id, label: team.name }))}
        />
        <PeopleSelect
          label={t("allRoles")}
          value={filters.get("role")}
          onChange={(value) => {
            filters.update("role", value);
          }}
          options={[
            ...new Set([
              ...members.map((member) => member.role),
              ...(props.accessView
                ? (props.bindings
                    ?.filter((binding) => binding.state === "active")
                    .map((binding) => binding.role) ?? [])
                : []),
            ]),
          ].map((role) => ({
            value: role,
            label: props.accessView ? roleTitle(role, a) : role,
          }))}
        />
        <PeopleSelect
          label={t("allStatuses")}
          value={filters.get("status")}
          onChange={(value) => {
            filters.update("status", value);
          }}
          options={["active", "suspended"].map((state) => ({ value: state, label: t(state) }))}
        />
        <CatalogChoiceMenu
          icon="sort"
          label={t("sortMembers")}
          options={["joined_desc", "joined", "name", "name_desc"].map((value) => ({
            label: t(value),
            active: sort === value,
            onSelect: () => {
              filters.update("sort", value);
            },
          }))}
        />
        <div className="col-span-2 flex items-center justify-between gap-2 lg:ml-auto">
          {props.accessView ? (
            context.capabilities.includes("binding.create") ? (
              <GrantAccessButton members={members} inspect={inspect} />
            ) : null
          ) : (
            <AddMemberDialog {...props} />
          )}
          <CatalogChoiceMenu
            icon="moreVertical"
            label={t("directoryActions")}
            align="end"
            options={[
              {
                label: t("downloadCsv"),
                icon: "download",
                onSelect: exportRows,
                disabled: !filtered.length,
              },
            ]}
          />
        </div>
      </div>
      {chosen.length ? (
        <MemberSelection
          count={chosen.length}
          clear={() => {
            setSelected([]);
          }}
        />
      ) : null}
      <CorporateMembersTable
        rows={rows}
        context={context}
        selected={selected}
        setSelected={setSelected}
        now={now}
        sort={sort}
        update={filters.update}
        empty={members.length === 0}
        accessView={props.accessView ?? false}
        bindings={props.bindings ?? []}
        inspect={inspect}
      />
      {props.accessView ? (
        <CorporateDetailDrawer
          open={Boolean(activeMember)}
          onOpenChange={(open) => {
            if (!open) inspect("");
          }}
          title={activeMember?.display_name ?? a("employee")}
          description={activeMember?.contact_email ?? ""}
        >
          {props.accessPanel}
        </CorporateDetailDrawer>
      ) : null}
      <PeoplePager
        total={filtered.length}
        page={page}
        kind="members"
        onPage={(value) => {
          filters.update("page", String(value));
        }}
      />
    </section>
  );
}

function GrantAccessButton({
  members,
  inspect,
}: {
  members: readonly CorporateMember[];
  inspect: (accountId: string) => void;
}) {
  const a = useTranslations("accessUi");
  const t = useTranslations("people");
  const [grantDialog, setGrantDialog] = useState(false);
  return (
    <>
      <Button
        onClick={() => {
          setGrantDialog(true);
        }}
        className="h-11"
      >
        <Icon name="plus" size="sm" />
        {a("grantAccess")}
      </Button>
      <Dialog open={grantDialog} onOpenChange={setGrantDialog}>
        <DialogContent closeLabel={t("close")}>
          <DialogTitle>{a("grantAccess")}</DialogTitle>
          <DialogDescription>{a("chooseEmployee")}</DialogDescription>
          <form
            className="mt-4 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const employee = new FormData(event.currentTarget).get("employee");
              if (typeof employee === "string" && employee) {
                setGrantDialog(false);
                inspect(employee);
              }
            }}
          >
            <select
              name="employee"
              aria-label={a("employee")}
              required
              className="border-input bg-background h-11 w-full rounded-sm border px-3 text-sm"
            >
              <option value="">{a("chooseEmployee")}</option>
              {members.map((member) => (
                <option key={member.account_id} value={member.account_id}>
                  {member.display_name ?? member.account_id}
                </option>
              ))}
            </select>
            <Button type="submit">{a("grantAccess")}</Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function exportMembers(members: readonly CorporateMember[], context: CorporateContext) {
  downloadPeopleCsv("members.csv", [
    ["name", "email", "job_title", "teams", "role", "status", "joined", "last_activity"],
    ...members.map((member) => [
      member.display_name ?? member.account_id,
      member.contact_email ?? "",
      member.job_title_name ?? "",
      context.teams
        .filter((team) => team.members.some((entry) => entry.account_id === member.account_id))
        .map((team) => team.name)
        .join("; "),
      member.role,
      member.state,
      member.joined_at ?? "",
      member.last_activity_at ?? "",
    ]),
  ]);
}

function MemberSelection({ count, clear }: { count: number; clear: () => void }) {
  const t = useTranslations("people");
  return (
    <div
      aria-live="polite"
      className="bg-muted flex items-center justify-between rounded-sm px-3 py-2 text-sm"
    >
      <span>{t("selected", { count })}</span>
      <Button variant="ghost" size="sm" type="button" onClick={clear}>
        {t("clearSelection")}
      </Button>
    </div>
  );
}

function useEmployeeSelection() {
  const router = useRouter();
  const pathname = usePathname();
  function inspect(accountId: string) {
    const params = new URLSearchParams(window.location.search);
    if (accountId) params.set("employee", accountId);
    else params.delete("employee");
    params.delete("detail");
    params.delete("scope");
    router.push(`${pathname}?${params.toString()}`, { scroll: false });
  }

  return inspect;
}
