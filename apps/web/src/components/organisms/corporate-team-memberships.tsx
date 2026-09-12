"use client";

import { useState, useTransition } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { corporateTeamAssignmentsAction } from "@/actions/corporate";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
import type { CorporateMember, CorporateTeamView } from "@/lib/api/generated/types.gen";

type Props = {
  team?: CorporateTeamView;
  employee?: CorporateMember;
  teams: readonly CorporateTeamView[];
  members: readonly CorporateMember[];
  organizationId: string;
  csrfToken: string;
  canManage: boolean;
};

// Both entry points operate the same team assignment contract.
// eslint-disable-next-line max-lines-per-function, complexity
export function CorporateTeamMemberships({
  team,
  employee,
  teams,
  members,
  organizationId,
  csrfToken,
  canManage,
}: Props) {
  const t = useTranslations("corporate");
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("available");
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [role, setRole] = useState<"staff" | "lead">("staff");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, startTransition] = useTransition();
  const roster = team
    ? team.members.map((member) => ({ team, member }))
    : teams.flatMap((item) => {
        const member = item.members.find((m) => m.account_id === employee?.account_id);
        return member ? [{ team: item, member }] : [];
      });
  const candidates = team
    ? members.map((member) => ({
        id: member.account_id,
        name: member.display_name ?? member.account_id,
        state: member.state,
        assigned: team.members.some((m) => m.account_id === member.account_id),
        teamNames: teams
          .filter((item) => item.members.some((m) => m.account_id === member.account_id))
          .map((item) => item.name),
      }))
    : teams.map((item) => ({
        id: item.team_id,
        name: item.name,
        state: item.state,
        assigned: item.members.some((m) => m.account_id === employee?.account_id),
        teamNames: [] as string[],
      }));
  const visible = candidates.filter(
    (item) =>
      item.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()) &&
      (filter === "all" || (filter === "available" ? !item.assigned : !item.teamNames.length)),
  );
  function change(
    assignments: Array<{
      accountId: string;
      teamId: string;
      role: "staff" | "lead";
      operation: "assign" | "remove";
      idempotencyKey: string;
    }>,
  ) {
    setMessage(null);
    startTransition(async () => {
      try {
        const result = await corporateTeamAssignmentsAction({
          organizationId,
          csrfToken,
          assignments,
        });
        setSelected((current) =>
          Object.fromEntries(
            Object.entries(current).filter(([, key]) => !result.completed.includes(key)),
          ),
        );
        setMessage(
          result.message
            ? `${t("batchPartial", { count: result.completed.length })} ${result.message}`
            : t("saved"),
        );
        if (!result.message) setAdding(false);
        router.refresh();
      } catch {
        setMessage(t("failed"));
        router.refresh();
      }
    });
  }
  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-medium">
          {t(team ? "members" : "teamMemberships")}{" "}
          <span className="text-muted-foreground text-base">({roster.length})</span>
        </h2>
        {canManage && team?.state !== "archived" && employee?.state !== "suspended" && (
          <Button
            onClick={() => {
              setAdding(!adding);
              setSelected({});
              setMessage(null);
            }}
            disabled={busy}
          >
            <Icon name="plus" size="sm" />
            {t(team ? "addEmployees" : "chooseTeams")}
          </Button>
        )}
      </div>
      {team?.state === "archived" && (
        <p className="bg-muted rounded-lg p-4 text-sm">{t("archivedTeamBody")}</p>
      )}
      {team && team.state === "active" && !team.lead_account_ids.length && (
        <p className="text-muted-foreground text-sm">{t("noActiveLead")}</p>
      )}
      {roster.length ? (
        <ul className="border-border divide-border divide-y rounded-lg border">
          {roster.map(({ team: item, member }) => (
            <li
              key={`${item.team_id}:${member.account_id}`}
              className="flex flex-wrap items-center justify-between gap-3 p-4"
            >
              <div className="min-w-0 space-y-1">
                <span className="font-medium">
                  {team ? (
                    (member.display_name ?? member.account_id)
                  ) : (
                    <Link href={`/corporate/teams/${item.team_id}`} className="hover:underline">
                      {item.name}
                    </Link>
                  )}
                </span>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{t(member.state)}</Badge>
                  <Badge variant="secondary">
                    {t(item.lead_account_ids.includes(member.account_id) ? "lead" : "staff")}
                  </Badge>
                  {!team && item.state === "archived" && (
                    <Badge variant="outline">{t("archived")}</Badge>
                  )}
                </div>
              </div>
              {canManage && (
                <div className="flex flex-wrap gap-2">
                  {item.state === "active" && member.state === "active" && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => {
                        change([
                          {
                            accountId: member.account_id,
                            teamId: item.team_id,
                            role: item.lead_account_ids.includes(member.account_id)
                              ? "staff"
                              : "lead",
                            operation: "assign",
                            idempotencyKey: crypto.randomUUID(),
                          },
                        ]);
                      }}
                    >
                      {t(
                        item.lead_account_ids.includes(member.account_id)
                          ? "makeStaff"
                          : "makeLead",
                      )}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() => {
                      if (!window.confirm(t("removeTeamConfirm"))) return;
                      change([
                        {
                          accountId: member.account_id,
                          teamId: item.team_id,
                          role: "staff",
                          operation: "remove",
                          idempotencyKey: crypto.randomUUID(),
                        },
                      ]);
                    }}
                  >
                    {t("removeFromTeam")}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <div className="border-border space-y-2 rounded-lg border border-dashed p-6">
          <p className="font-medium">{t(team ? "emptyTeam" : "noEmployeeTeams")}</p>
          {team && canManage && (
            <p className="text-muted-foreground max-w-prose text-sm">{t("emptyTeamBody")}</p>
          )}
        </div>
      )}
      {adding && (
        <form
          className="border-border bg-card space-y-4 rounded-lg border p-5"
          onSubmit={(event) => {
            event.preventDefault();
            change(
              Object.entries(selected).map(([id, idempotencyKey]) => ({
                accountId: team ? id : (employee?.account_id ?? ""),
                teamId: team?.team_id ?? id,
                role,
                operation: "assign",
                idempotencyKey,
              })),
            );
          }}
        >
          <h3 className="text-lg font-medium">{t(team ? "addEmployees" : "chooseTeams")}</h3>
          <div className="flex flex-wrap gap-3">
            <div className="min-w-48 flex-1 space-y-2">
              <Label htmlFor="membership-search">
                {t(team ? "searchEmployees" : "searchTeams")}
              </Label>
              <Input
                id="membership-search"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="membership-filter">{t("membershipFilter")}</Label>
              <select
                id="membership-filter"
                value={filter}
                onChange={(event) => {
                  setFilter(event.target.value);
                }}
                className="border-input bg-background h-9 rounded-sm border px-3 text-sm"
              >
                <option value="available">{t(team ? "notInThisTeam" : "allTeams")}</option>
                <option value="all">{t(team ? "allEmployees" : "allTeams")}</option>
                {team && <option value="unassigned">{t("unassigned")}</option>}
              </select>
            </div>
          </div>
          {!candidates.length && (
            <p className="text-muted-foreground text-sm">
              {t(team ? "noOrganizationEmployees" : "noTeams")}
            </p>
          )}
          <ul className="border-border divide-border max-h-72 overflow-y-auto rounded-sm border">
            {visible.map((item) => (
              <li key={item.id}>
                <label className="hover:bg-muted flex min-h-14 cursor-pointer items-center gap-3 px-3 py-2">
                  <input
                    type="checkbox"
                    checked={Object.hasOwn(selected, item.id)}
                    disabled={busy || item.assigned || item.state !== "active"}
                    onChange={(event) => {
                      setSelected((current) => {
                        const next = { ...current };
                        if (event.target.checked) next[item.id] = crypto.randomUUID();
                        else
                          return Object.fromEntries(
                            Object.entries(current).filter(([id]) => id !== item.id),
                          );
                        return next;
                      });
                    }}
                    className="accent-primary h-4 w-4"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{item.name}</span>
                    {team && (
                      <span className="text-muted-foreground block text-xs">
                        {item.teamNames.join(", ") || t("unassigned")}
                      </span>
                    )}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {item.assigned ? t("assigned") : t(item.state)}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          {!!candidates.length && !visible.length && (
            <p className="text-muted-foreground text-sm">{t("noMatches")}</p>
          )}
          <div className="space-y-2">
            <Label htmlFor="membership-role">{t("teamRole")}</Label>
            <select
              id="membership-role"
              value={role}
              disabled={busy}
              onChange={(event) => {
                setRole(event.target.value === "lead" ? "lead" : "staff");
                setSelected((current) =>
                  Object.fromEntries(Object.keys(current).map((id) => [id, crypto.randomUUID()])),
                );
              }}
              className="border-input bg-background h-9 rounded-sm border px-3 text-sm"
            >
              <option value="staff">{t("staff")}</option>
              <option value="lead">{t("lead")}</option>
            </select>
            <p className="text-muted-foreground text-sm">{t("teamRoleHint")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={busy || !Object.keys(selected).length}>
              {busy ? t("saving") : t("addSelected", { count: Object.keys(selected).length })}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => {
                setAdding(false);
                setSelected({});
              }}
            >
              {t("cancel")}
            </Button>
          </div>
        </form>
      )}
      {message && (
        <p role="status" className="text-sm">
          {message}
        </p>
      )}
    </section>
  );
}
