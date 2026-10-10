"use client";

import { useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { CatalogChoiceMenu } from "@/components/molecules/catalog-choice-menu";
import {
  PEOPLE_PAGE_SIZE,
  PeoplePager,
  PeopleSearch,
  PeopleSelect,
  usePeopleFilters,
  CorporateDetailDrawer,
} from "@/components/organisms/corporate-people-ui";
import { CorporateGrantAccessDialog } from "@/components/organisms/corporate-grant-access-dialog";
import {
  BulkMembersDialog,
  EditMemberDialog,
} from "@/components/organisms/corporate-member-edit-dialogs";
import type {
  CorporateContext,
  CorporateJobTitleView,
  CorporateMember,
  CorporatePermissionDefinition,
  CorporateRoleView,
  CorporateBinding,
} from "@/lib/api/generated/types.gen";
import { downloadPeopleCsv } from "@/lib/member-export";
import { CorporateMembersTable } from "@/components/organisms/corporate-members-table";
import { Icon } from "@/theme";
import { useRouter as useI18nRouter, usePathname } from "@/lib/i18n/navigation";
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
  /** Data for the Grant access dialog on the employee-access view. */
  grantAccess?: {
    grantableRoleNames: readonly string[] | null;
    definitions: readonly CorporatePermissionDefinition[];
    scopeOptions: readonly { value: string; label: string }[];
  };
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

/** This administration table extends the directory kit with membership-specific columns and selection. */
export function CorporateMembersDirectory(props: Props) {
  const { members, context, now } = props;
  const t = useTranslations("people");
  const a = useTranslations("accessUi");
  const inspect = useEmployeeSelection();
  const filters = usePeopleFilters();
  const activeMember = members.find((member) => member.account_id === filters.get("employee"));
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<CorporateMember | null>(null);
  const [bulkEdit, setBulkEdit] = useState(false);
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
  const canEditMembers =
    context.capabilities.includes("member.update") ||
    context.capabilities.includes("member.manage");
  const exportRows = () => {
    exportMembers(chosen.length ? chosen : filtered, context);
  };

  return (
    <section
      aria-label={props.accessView ? a("employeeAccess") : t("members")}
      className={`min-w-0 space-y-4 ${props.accessView && activeMember ? "2xl:pr-[27rem]" : ""}`}
      data-ui={props.accessView ? "employee-access-directory" : "members-directory"}
    >
      <DirectoryToolbar
        members={members}
        context={context}
        roles={props.roles}
        csrfToken={props.csrfToken}
        grantAccess={props.grantAccess}
        filters={filters}
        sort={sort}
        accessView={props.accessView ?? false}
        bindings={props.bindings ?? []}
        canExport={filtered.length > 0}
        onExport={exportRows}
      />
      {chosen.length ? (
        <MemberSelection
          count={chosen.length}
          canEdit={canEditMembers && !props.accessView}
          onEdit={() => {
            setBulkEdit(true);
          }}
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
        onEdit={canEditMembers ? setEditing : undefined}
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
      <EditMemberDialog
        member={editing}
        context={context}
        roles={props.roles}
        jobTitles={props.jobTitles}
        csrfToken={props.csrfToken}
        onClose={() => {
          setEditing(null);
        }}
      />
      <BulkMembersDialog
        open={bulkEdit}
        members={chosen}
        context={context}
        roles={props.roles}
        jobTitles={props.jobTitles}
        csrfToken={props.csrfToken}
        onClose={() => {
          setBulkEdit(false);
        }}
      />
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

function DirectoryToolbar({
  members,
  context,
  roles,
  csrfToken,
  grantAccess,
  filters,
  sort,
  accessView,
  bindings,
  canExport,
  onExport,
}: {
  members: readonly CorporateMember[];
  context: CorporateContext;
  roles: readonly CorporateRoleView[];
  csrfToken: string;
  grantAccess: Props["grantAccess"];
  filters: ReturnType<typeof usePeopleFilters>;
  sort: string;
  accessView: boolean;
  bindings: readonly CorporateBinding[];
  canExport: boolean;
  onExport: () => void;
}) {
  const t = useTranslations("people");
  const a = useTranslations("accessUi");
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="min-w-0 basis-full xl:flex-1">
        <PeopleSearch
          label={accessView ? a("searchEmployees") : t("searchMembers")}
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
            ...(accessView
              ? bindings
                  .filter((binding) => binding.state === "active")
                  .map((binding) => binding.role)
              : []),
          ]),
        ].map((role) => ({
          value: role,
          label: accessView ? roleTitle(role, a) : role,
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
        {accessView && grantAccess && context.capabilities.includes("binding.create") ? (
          <GrantAccessButton
            members={members}
            context={context}
            roles={roles}
            csrfToken={csrfToken}
            grantAccess={grantAccess}
          />
        ) : null}
        <CatalogChoiceMenu
          icon="moreVertical"
          label={t("directoryActions")}
          align="end"
          options={[
            {
              label: t("downloadCsv"),
              icon: "download",
              onSelect: onExport,
              disabled: !canExport,
            },
          ]}
        />
      </div>
    </div>
  );
}

function GrantAccessButton({
  members,
  context,
  roles,
  csrfToken,
  grantAccess,
}: {
  members: readonly CorporateMember[];
  context: CorporateContext;
  roles: readonly CorporateRoleView[];
  csrfToken: string;
  grantAccess: NonNullable<Props["grantAccess"]>;
}) {
  const a = useTranslations("accessUi");
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
      <CorporateGrantAccessDialog
        open={grantDialog}
        onOpenChange={setGrantDialog}
        csrfToken={csrfToken}
        organizationId={context.organization.organization_id}
        authorizationRevision={context.organization.authorization_revision}
        members={members}
        roles={roles}
        grantableRoleNames={grantAccess.grantableRoleNames}
        teams={context.teams}
        projects={context.projects}
        scopeOptions={grantAccess.scopeOptions}
        definitions={grantAccess.definitions}
        capabilities={context.capabilities}
      />
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

function MemberSelection({
  count,
  canEdit,
  onEdit,
  clear,
}: {
  count: number;
  canEdit: boolean;
  onEdit: () => void;
  clear: () => void;
}) {
  const t = useTranslations("people");
  return (
    <div
      aria-live="polite"
      className="bg-muted flex items-center justify-between rounded-sm px-3 py-2 text-sm"
    >
      <span>{t("selected", { count })}</span>
      <div className="flex items-center gap-2">
        {canEdit ? (
          <Button variant="ghost" size="sm" type="button" onClick={onEdit}>
            {t("editSelected")}
          </Button>
        ) : null}
        <Button variant="ghost" size="sm" type="button" onClick={clear}>
          {t("clearSelection")}
        </Button>
      </div>
    </div>
  );
}

function useEmployeeSelection() {
  const router = useI18nRouter();
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
