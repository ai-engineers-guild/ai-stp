"use client";

import { useState } from "react";
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
  PeopleSearch,
  PeopleSelect,
  usePeopleFilters,
} from "@/components/molecules/people-ui";
import { PagePager } from "@/components/molecules/page-pager";
import type {
  CorporateContext,
  CorporateJobTitleView,
  CorporateMember,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";
import { downloadPeopleCsv } from "@/lib/member-export";
import { CorporateMembersTable } from "@/components/organisms/corporate-members-table";
import { Icon } from "@/theme";

type Props = {
  members: readonly CorporateMember[];
  context: CorporateContext;
  roles: readonly CorporateRoleView[];
  jobTitles: readonly CorporateJobTitleView[];
  csrfToken: string;
  now: string;
};

export function selectPeopleMembers(
  members: readonly CorporateMember[],
  context: CorporateContext,
  filters: { query: string; team: string; role: string; status: string; sort: string },
) {
  const query = filters.query.trim().toLowerCase();
  const result = members.filter(
    (member) =>
      (!query ||
        [member.display_name, member.contact_email, member.job_title_name, member.role].some(
          (value) => value?.toLowerCase().includes(query),
        )) &&
      (!filters.role || member.role === filters.role) &&
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
  const filters = usePeopleFilters();
  const [selected, setSelected] = useState<string[]>([]);
  const sort = filters.get("sort") || "joined_desc";
  const filtered = selectPeopleMembers(members, context, {
    query: filters.get("query"),
    team: filters.get("team"),
    role: filters.get("role"),
    status: filters.get("status"),
    sort,
  });
  const page = Math.min(
    Math.max(1, Number(filters.get("page")) || 1),
    Math.max(1, Math.ceil(filtered.length / PEOPLE_PAGE_SIZE)),
  );
  const rows = filtered.slice((page - 1) * PEOPLE_PAGE_SIZE, page * PEOPLE_PAGE_SIZE);
  const chosen = filtered.filter((member) => selected.includes(member.account_id));
  function exportRows() {
    downloadPeopleCsv("members.csv", [
      ["name", "email", "job_title", "teams", "role", "status", "joined", "last_activity"],
      ...(chosen.length ? chosen : filtered).map((member) => [
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
  return (
    <section aria-label={t("members")} className="min-w-0 space-y-4" data-ui="members-directory">
      <div className="grid grid-cols-2 items-center gap-3 lg:flex lg:flex-wrap">
        <div className="col-span-2 min-w-0 lg:flex-1">
          <PeopleSearch
            label={t("searchMembers")}
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
          options={[...new Set(members.map((member) => member.role))].map((role) => ({
            value: role,
            label: role,
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
          <AddMemberDialog {...props} />
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
        <div
          aria-live="polite"
          className="bg-muted flex items-center justify-between rounded-sm px-3 py-2 text-sm"
        >
          <span>{t("selected", { count: chosen.length })}</span>
          <Button
            variant="ghost"
            size="sm"
            type="button"
            onClick={() => {
              setSelected([]);
            }}
          >
            {t("clearSelection")}
          </Button>
        </div>
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
      />
      <PagePager
        label={t("pagination")}
        page={page}
        totalPages={Math.max(1, Math.ceil(filtered.length / PEOPLE_PAGE_SIZE))}
        summary={
          <p aria-live="polite" className="text-muted-foreground text-sm tabular-nums">
            {t("showingMembers", {
              start: filtered.length ? (page - 1) * PEOPLE_PAGE_SIZE + 1 : 0,
              end: Math.min(page * PEOPLE_PAGE_SIZE, filtered.length),
              total: filtered.length,
            })}
          </p>
        }
        controls={{
          previous: t("previousPage"),
          next: t("nextPage"),
          page: (value) => t("page", { page: value }),
        }}
        onPage={(value) => {
          filters.update("page", String(value));
        }}
      />
    </section>
  );
}
