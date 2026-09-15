"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Label } from "@/components/atoms/label";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import {
  useGovernanceMutation,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import { Link } from "@/lib/i18n/navigation";
import type { ProjectTeamView } from "@/lib/api/generated/types.gen";

export function ProjectTeamEditor({
  projectId,
  teams,
  relations,
  capabilities,
  ...authority
}: GovernanceAuthority & {
  projectId: string;
  teams: { team_id: string; name: string }[];
  relations: ProjectTeamView[];
  capabilities: string[];
}) {
  const h = useTranslations("hub");
  const mutation = useGovernanceMutation(authority);
  const [selected, setSelected] = useState("");
  const current = relations.find((item) => item.team_id === selected);
  const active = relations.filter((item) => item.state === "current");
  const [role, setRole] = useState<ProjectTeamView["role"]>("contributor");
  const canSave = capabilities.includes(`project_team.${current ? "update" : "create"}`);
  const owner = active.find((item) => item.role === "owner" && item.team_id !== selected);
  const path = `/v1/corporate/organizations/${authority.organizationId}/projects/${projectId}/teams`;
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-medium">{h("teams")}</h2>
      <ul className="divide-border divide-y">
        {active.map((item) => (
          <li
            key={item.relation_id}
            className="flex flex-wrap items-center justify-between gap-3 py-3"
          >
            <Link
              href={`/corporate/teams/${item.team_id}`}
              className="min-h-11 py-3 underline underline-offset-4"
            >
              {teams.find((team) => team.team_id === item.team_id)?.name ?? h("teams")}
            </Link>
            <span className="text-muted-foreground text-sm">{h(item.role)}</span>
            {capabilities.includes("project_team.delete") && (
              <Button
                variant="outline"
                disabled={mutation.busy}
                onClick={() => {
                  mutation.save(
                    path,
                    {
                      team_id: item.team_id,
                      expected_revision: item.revision,
                      role: item.role,
                      state: "retired",
                    },
                    "PUT",
                    () => {
                      setSelected("");
                    },
                  );
                }}
              >
                {h("unlink")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {capabilities.some(
        (item) => item === "project_team.create" || item === "project_team.update",
      ) && (
        <details>
          <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
            {h("linkTeam")}
          </summary>
          <form
            className="max-w-xl space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              if (!selected || !canSave) return;
              mutation.save(
                path,
                {
                  team_id: selected,
                  expected_revision: current?.revision ?? 0,
                  role,
                  state: "current",
                  ...(role === "owner" && owner
                    ? {
                        replace_owner_relation_id: owner.relation_id,
                        replace_owner_expected_revision: owner.revision,
                      }
                    : {}),
                },
                "PUT",
                () => {
                  setSelected("");
                },
              );
            }}
          >
            <fieldset disabled={mutation.busy} className="space-y-4">
              <SearchableMultiSelect
                key={selected}
                name="team_id"
                label={h("teams")}
                searchLabel={h("search")}
                options={teams.map((item) => ({ value: item.team_id, label: item.name }))}
                selected={selected ? [selected] : []}
                multiple={false}
                onChange={(values) => {
                  const id = values[0] ?? "";
                  setSelected(id);
                  setRole(relations.find((item) => item.team_id === id)?.role ?? "contributor");
                }}
              />
              <Label htmlFor="project-team-role">{h("teamRole")}</Label>
              <select
                id="project-team-role"
                className="border-input bg-background min-h-11 w-full rounded-sm border px-3 text-sm"
                value={role}
                onChange={(event) => {
                  const value = event.target.value;
                  if (value === "owner" || value === "responsible" || value === "contributor")
                    setRole(value);
                }}
              >
                {(["contributor", "responsible", "owner"] as const).map((value) => (
                  <option key={value} value={value}>
                    {h(value)}
                  </option>
                ))}
              </select>
              {role === "owner" && owner && (
                <p className="text-muted-foreground text-sm">{h("replaceOwner")}</p>
              )}
              <Button type="submit" disabled={!selected || !canSave}>
                {h("save")}
              </Button>
            </fieldset>
          </form>
        </details>
      )}
      {mutation.message && (
        <p role="status" className="text-sm">
          {mutation.message}
        </p>
      )}
    </section>
  );
}
