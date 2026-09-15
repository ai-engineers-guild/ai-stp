"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { Label } from "@/components/atoms/label";
import {
  useGovernanceMutation,
  type GovernanceAuthority,
} from "@/components/organisms/corporate-governance-controls";
import type { TechnologyDecisionView, TechnologyTeamView } from "@/lib/api/generated/types.gen";

const selectClass =
  "border-input bg-background text-foreground focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-sm focus-visible:ring-2";

function formText(data: FormData, name: string) {
  const value = data.get(name);
  return typeof value === "string" ? value.trim() : "";
}

export function TechnologyDecisionEditor({
  technologyId,
  initial,
  capabilities,
  employees = [],
  ...authority
}: GovernanceAuthority & {
  technologyId: string;
  initial?: TechnologyDecisionView;
  capabilities: string[];
  employees?: { value: string; label: string }[];
}) {
  const t = useTranslations("technology");
  const h = useTranslations("hub");
  const [snapshot, setSnapshot] = useState(initial ?? null);
  const mutation = useGovernanceMutation(authority);
  const canApprove = capabilities.includes("technology.approve");
  const canSave = capabilities.includes(
    snapshot ? "technology_decision.update" : "technology_decision.create",
  );
  const canClear =
    snapshot !== null &&
    capabilities.includes("technology_decision.delete") &&
    (!snapshot.approved || canApprove);
  const path = `/v1/corporate/organizations/${authority.organizationId}/technologies/${technologyId}/decision`;
  return (
    <section className="max-w-prose space-y-4" aria-busy={mutation.busy}>
      <h2 className="text-xl font-medium">{t(snapshot ? "editDecision" : "createDecision")}</h2>
      <form
        key={snapshot?.revision ?? 0}
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (!canSave) return;
          const data = new FormData(event.currentTarget);
          const lead = formText(data, "lead_account_id");
          const adoption = data.get("adoption");
          if (lead && !/^account_[0-9A-HJKMNP-TV-Z]{26}$/.test(lead)) return;
          if (
            adoption !== "none" &&
            adoption !== "assess" &&
            adoption !== "trial" &&
            adoption !== "adopt" &&
            adoption !== "hold"
          )
            return;
          const approved = canApprove
            ? data.get("approved") === "on"
            : (snapshot?.approved ?? false);
          const effect = {
            expected_revision: snapshot?.revision ?? 0,
            lead_account_id: lead || null,
            approved,
            adoption,
          };
          mutation.save(path, effect, "PUT", () => {
            setSnapshot({
              technology_id: technologyId,
              revision: (snapshot?.revision ?? 0) + 1,
              lead_account_id: lead || null,
              approved,
              adoption,
            });
          });
        }}
      >
        <fieldset disabled={mutation.busy || !canSave} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor={`lead-${technologyId}`}>{t("responsibleLead")}</Label>
            <SearchableMultiSelect
              name="lead_account_id"
              label={t("responsibleLead")}
              searchLabel={h("search")}
              options={employees}
              selected={snapshot?.lead_account_id ? [snapshot.lead_account_id] : []}
              multiple={false}
              closeLabel={h("cancel")}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`adoption-${technologyId}`}>{t("adoption")}</Label>
            <select
              id={`adoption-${technologyId}`}
              name="adoption"
              defaultValue={snapshot?.adoption ?? "none"}
              className={selectClass}
            >
              {["none", "assess", "trial", "adopt", "hold"].map((value) => (
                <option key={value} value={value}>
                  {t(`values.${value}`)}
                </option>
              ))}
            </select>
          </div>
          <label className="flex min-h-11 items-center gap-2">
            <input
              name="approved"
              type="checkbox"
              defaultChecked={snapshot?.approved ?? false}
              disabled={!canApprove}
            />
            {t("approvedDecision")}
          </label>
        </fieldset>
        <Button size="lg" type="submit" disabled={mutation.busy || !canSave}>
          {t(mutation.busy ? "saving" : "saveChanges")}
        </Button>
      </form>
      {canClear && (
        <Button
          size="lg"
          variant="outline"
          disabled={mutation.busy}
          onClick={() => {
            mutation.save(path, { expected_revision: snapshot.revision }, "DELETE", () => {
              setSnapshot({
                technology_id: technologyId,
                revision: snapshot.revision + 1,
                lead_account_id: null,
                approved: false,
                adoption: "none",
              });
            });
          }}
        >
          {t("clearDecision")}
        </Button>
      )}
      {mutation.message && <p role="status">{mutation.message}</p>}
    </section>
  );
}

export function TechnologyTeamEditor({
  technologyId,
  initial,
  capabilities,
  teams = [],
  relations = [],
  ...authority
}: GovernanceAuthority & {
  technologyId: string;
  initial?: TechnologyTeamView;
  capabilities: string[];
  teams?: { value: string; label: string }[];
  relations?: TechnologyTeamView[];
}) {
  const t = useTranslations("technology");
  const h = useTranslations("hub");
  const revision = useRef(initial?.revision ?? 0);
  const [selectedTeam, setSelectedTeam] = useState<string[]>(
    initial?.team_id ? [initial.team_id] : [],
  );
  const [acknowledged, setAcknowledged] = useState(initial !== undefined);
  const mutation = useGovernanceMutation(authority);
  const canSave = capabilities.includes(
    acknowledged ? "technology_team.update" : "technology_team.create",
  );
  return (
    <form
      className="max-w-prose space-y-4"
      aria-busy={mutation.busy}
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const team = formText(data, "team_id");
        const state = data.get("state");
        if (
          !/^operation_[0-9A-HJKMNP-TV-Z]{26}$/.test(team) ||
          (state !== "current" && state !== "retired")
        )
          return;
        if (
          !capabilities.includes(
            state === "retired"
              ? "technology_team.delete"
              : acknowledged
                ? "technology_team.update"
                : "technology_team.create",
          )
        )
          return;
        mutation.save(
          `/v1/corporate/organizations/${authority.organizationId}/technologies/${technologyId}/responsible-teams`,
          { team_id: team, state, expected_revision: revision.current },
          "PUT",
          () => {
            revision.current += 1;
            setAcknowledged(true);
          },
        );
      }}
    >
      <h3 className="text-lg font-medium">
        {t(initial ? "editResponsibility" : "createResponsibility")}
      </h3>
      <fieldset disabled={mutation.busy} className="space-y-4">
        <div className="space-y-2">
          <SearchableMultiSelect
            name="team_id"
            label={h("teams")}
            searchLabel={h("search")}
            options={initial ? teams.filter((item) => item.value === initial.team_id) : teams}
            selected={selectedTeam}
            multiple={false}
            closeLabel={h("cancel")}
            onChange={(values) => {
              if (initial) return;
              setSelectedTeam(values);
              const relation = relations.find((item) => item.team_id === values[0]);
              revision.current = relation?.revision ?? 0;
              setAcknowledged(relation !== undefined);
            }}
          />
        </div>
        <input type="hidden" name="state" value="current" />
      </fieldset>
      <Button type="submit" size="lg" disabled={mutation.busy || !canSave}>
        {t(mutation.busy ? "saving" : "saveChanges")}
      </Button>
      {initial?.state === "current" && capabilities.includes("technology_team.delete") && (
        <Button
          type="button"
          variant="outline"
          disabled={mutation.busy}
          onClick={() => {
            mutation.save(
              `/v1/corporate/organizations/${authority.organizationId}/technologies/${technologyId}/responsible-teams`,
              { team_id: initial.team_id, state: "retired", expected_revision: revision.current },
              "PUT",
              () => {
                revision.current += 1;
              },
            );
          }}
        >
          {h("unlink")}
        </Button>
      )}
      {mutation.message && <p role="status">{mutation.message}</p>}
    </form>
  );
}
