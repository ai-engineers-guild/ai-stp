"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/atoms/badge";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Link } from "@/lib/i18n/navigation";
import type { CorporateMember, CorporateTeamView } from "@/lib/api/generated/types.gen";

export function CorporateEmployeeDirectory({
  members,
  teams,
}: {
  members: readonly CorporateMember[];
  teams: readonly CorporateTeamView[];
}) {
  const t = useTranslations("corporate");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const visible = members
    .map((member) => ({
      member,
      memberships: teams.filter((team) =>
        team.members.some((item) => item.account_id === member.account_id),
      ),
    }))
    .filter(
      ({ member, memberships }) =>
        (member.display_name ?? member.account_id)
          .toLocaleLowerCase()
          .includes(search.toLocaleLowerCase()) &&
        (filter === "all" ||
          (filter === "unassigned"
            ? !memberships.length
            : memberships.some((team) => team.team_id === filter))),
    );
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-medium">
        {t("members")} <span className="text-muted-foreground text-base">({members.length})</span>
      </h2>
      <div className="flex flex-wrap gap-3">
        <div className="min-w-48 flex-1 space-y-2">
          <Label htmlFor="employee-search">{t("searchEmployees")}</Label>
          <Input
            id="employee-search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="employee-team-filter">{t("teamFilter")}</Label>
          <select
            id="employee-team-filter"
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
            }}
            className="border-input bg-background h-9 max-w-full rounded-sm border px-3 text-sm"
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
      {visible.length ? (
        <ul className="border-border divide-border divide-y rounded-lg border">
          {visible.map(({ member, memberships }) => (
            <li key={member.account_id}>
              <Link
                href={`/corporate/members/${member.account_id}`}
                className="hover:bg-muted focus-visible:ring-ring flex flex-wrap items-center justify-between gap-3 p-4 outline-none focus-visible:ring-2"
              >
                <div className="min-w-0 space-y-1 [overflow-wrap:anywhere]">
                  <span className="block font-medium">
                    {member.display_name ?? member.account_id}
                  </span>
                  <span className="text-muted-foreground block text-sm">
                    {memberships.map((team) => team.name).join(", ") || t("unassigned")}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{t(member.state)}</Badge>
                  <Badge variant="secondary">{member.role}</Badge>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground py-6 text-sm">
          {t(members.length ? "noMatches" : "noOrganizationEmployees")}
        </p>
      )}
    </section>
  );
}
