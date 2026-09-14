"use client";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import {
  CorporateDirectoryResults,
  type DirectoryItem,
} from "@/components/organisms/corporate-directory-results";
import type { CorporateMember, CorporateTeamView } from "@/lib/api/generated/types.gen";

function initialFilter(name: "query" | "team_filter", fallback: string): string {
  if (typeof window === "undefined") return fallback;
  return new URLSearchParams(window.location.search).get(name) ?? fallback;
}

export function CorporateEmployeeDirectory({
  members,
  teams,
  items,
}: {
  members: readonly CorporateMember[];
  teams: readonly CorporateTeamView[];
  items?: readonly DirectoryItem[];
}) {
  const t = useTranslations("corporate");
  const hub = useTranslations("hub");
  const [search, setSearch] = useState(() => initialFilter("query", ""));
  const [filter, setFilter] = useState(() => initialFilter("team_filter", "all"));
  useEffect(() => {
    function restore() {
      const params = new URLSearchParams(window.location.search);
      setSearch(params.get("query") ?? "");
      setFilter(params.get("team_filter") ?? "all");
    }
    window.addEventListener("popstate", restore);
    return () => {
      window.removeEventListener("popstate", restore);
    };
  }, []);
  const employees =
    items ??
    members.map((member) => {
      const memberships = teams.filter((team) =>
        team.members.some((item) => item.account_id === member.account_id),
      );
      return {
        id: member.account_id,
        name: member.display_name?.trim() || hub("unknownEmployee"),
        state: member.state,
        role: member.role,
        teams: memberships.map((team) => ({ id: team.team_id, name: team.name })),
        is_lead: teams.some((team) => team.lead_account_ids.includes(member.account_id)),
      };
    });
  function updateUrl(nextSearch: string, nextFilter: string) {
    const url = new URL(window.location.href);
    if (nextSearch) url.searchParams.set("query", nextSearch);
    else url.searchParams.delete("query");
    if (nextFilter === "all") url.searchParams.delete("team_filter");
    else url.searchParams.set("team_filter", nextFilter);
    window.history.replaceState(window.history.state, "", url);
  }
  const visible = employees.filter((item) => {
    const matchesSearch = item.name.toLocaleLowerCase().includes(search.toLocaleLowerCase());
    const memberships = item.teams ?? [];
    const matchesTeam =
      filter === "all" ||
      (filter === "unassigned"
        ? memberships.length === 0
        : memberships.some((team) => team.id === filter));
    return matchesSearch && matchesTeam;
  });
  return (
    <section className="min-w-0 space-y-4">
      <h2 className="text-xl font-medium">{t("members")}</h2>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48 flex-1 space-y-2">
          <Label htmlFor="employee-search">{t("searchEmployees")}</Label>
          <Input
            id="employee-search"
            type="search"
            value={search}
            onChange={(event) => {
              const nextSearch = event.target.value;
              setSearch(nextSearch);
              updateUrl(nextSearch, filter);
            }}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="employee-team-filter">{t("teamFilter")}</Label>
          <select
            id="employee-team-filter"
            value={filter}
            onChange={(event) => {
              const nextFilter = event.target.value;
              setFilter(nextFilter);
              updateUrl(search, nextFilter);
            }}
            className="border-input bg-background min-h-11 max-w-full rounded-sm border px-3 text-sm"
          >
            <option value="all">{t("allEmployees")}</option>
            <option value="unassigned">{t("unassigned")}</option>
            {teams.map((team) => (
              <option key={team.team_id} value={team.team_id}>
                {team.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <CorporateDirectoryResults resource="members" items={visible} />
    </section>
  );
}
