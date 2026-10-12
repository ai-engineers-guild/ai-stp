"use client";
import { Select } from "@/components/atoms/select";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { FormDialog } from "@/components/molecules/form-dialog";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { corporateMutation } from "@/lib/api/corporate-mutation";
import {
  applyBulkChange,
  baseBody,
  fieldValue,
  readRevision,
  saveTeams,
} from "@/lib/api/corporate-member-mutations";
import { peopleSelectClass } from "@/components/molecules/people-ui";
import type {
  CorporateContext,
  CorporateJobTitleView,
  CorporateMember,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";

type SharedProps = {
  context: CorporateContext;
  roles: readonly CorporateRoleView[];
  jobTitles: readonly CorporateJobTitleView[];
  csrfToken: string;
};

export function EditMemberDialog({
  member,
  context,
  roles,
  jobTitles,
  csrfToken,
  onClose,
}: SharedProps & {
  member: CorporateMember | null;
  onClose: () => void;
}) {
  const t = useTranslations("people");
  const c = useTranslations("corporate");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const organizationId = context.organization.organization_id;
  const authorizationRevision = context.organization.authorization_revision;
  const canMemberUpdate = context.capabilities.includes("member.update");
  const canAssign = context.capabilities.includes("member.manage");

  return (
    <FormDialog
      open={member !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={t("editMember")}
      description={member?.contact_email ?? member?.account_id ?? ""}
      closeLabel={t("close")}
      cancelLabel={c("cancel")}
      submitLabel={c("update")}
      busyLabel={c("saving")}
      busy={busy}
      error={error}
      onSubmit={(event) => {
        if (!member) return;
        setError(null);
        const data = new FormData(event.currentTarget);
        const name = fieldValue(data, "displayName");
        const role = fieldValue(data, "role") || member.role;
        const state = fieldValue(data, "state") || member.state;
        const jobTitleId = canMemberUpdate
          ? fieldValue(data, "jobTitle") || null
          : member.job_title_id;
        const teamIds = data.getAll("teams").map(String);
        const leadIds = new Set(data.getAll("teamLeads").map(String));
        startTransition(async () => {
          let failed: string | null = null;
          let revision = member.revision;
          if (name && name !== (member.display_name ?? "")) {
            const result = await corporateMutation({
              csrfToken,
              organizationId,
              path: `/v1/corporate/organizations/${organizationId}/members/${member.account_id}/profile`,
              method: "PATCH",
              body: {
                ...baseBody(revision, authorizationRevision),
                display_name: name,
                idempotency_key: crypto.randomUUID(),
              },
            });
            if (!result.ok) failed = result.message;
            else revision = readRevision(result.data) ?? revision;
          }
          if (
            canMemberUpdate &&
            !failed &&
            (role !== member.role || state !== member.state || jobTitleId !== member.job_title_id)
          ) {
            const result = await corporateMutation({
              csrfToken,
              organizationId,
              path: `/v1/corporate/organizations/${organizationId}/members/${member.account_id}`,
              method: "PATCH",
              body: {
                ...baseBody(revision, authorizationRevision),
                role,
                state,
                job_title_id: jobTitleId,
                idempotency_key: crypto.randomUUID(),
              },
            });
            if (!result.ok) failed = result.message;
            else revision = readRevision(result.data) ?? revision;
          }
          if (canAssign && !failed) {
            const result = await saveTeams(member, context, csrfToken, teamIds, leadIds);
            if (result) failed = result;
          }
          if (failed) {
            setError(failed);
            router.refresh();
            return;
          }
          onClose();
          router.refresh();
        });
      }}
    >
      {member ? (
        <EditMemberFields
          key={member.account_id}
          member={member}
          context={context}
          roles={roles}
          jobTitles={jobTitles}
          canMemberUpdate={canMemberUpdate}
          canAssign={canAssign}
        />
      ) : null}
    </FormDialog>
  );
}

function EditMemberFields({
  member,
  context,
  roles,
  jobTitles,
  canMemberUpdate,
  canAssign,
}: {
  member: CorporateMember;
  context: CorporateContext;
  roles: readonly CorporateRoleView[];
  jobTitles: readonly CorporateJobTitleView[];
  canMemberUpdate: boolean;
  canAssign: boolean;
}) {
  const t = useTranslations("people");
  const c = useTranslations("corporate");
  const memberTeams = context.teams.filter((team) =>
    team.members.some((entry) => entry.account_id === member.account_id),
  );
  const [teamIds, setTeamIds] = useState<string[]>(memberTeams.map((team) => team.team_id));
  const [leadIds, setLeadIds] = useState<string[]>(
    context.teams
      .filter((team) => team.lead_account_ids.includes(member.account_id))
      .map((team) => team.team_id),
  );
  const teamOptions = context.teams.map((team) => ({ value: team.team_id, label: team.name }));
  const roleNames = roles.some((role) => role.name === member.role)
    ? roles.map((role) => role.name)
    : [member.role, ...roles.map((role) => role.name)];
  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="member-display-name">{c("displayName")}</Label>
        <Input
          id="member-display-name"
          name="displayName"
          maxLength={80}
          defaultValue={member.display_name ?? ""}
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="member-role">{t("role")}</Label>
          <Select
            id="member-role"
            name="role"
            defaultValue={member.role}
            disabled={!canMemberUpdate}
            className={peopleSelectClass}
          >
            {roleNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="member-state">{t("status")}</Label>
          <Select
            id="member-state"
            name="state"
            defaultValue={member.state}
            disabled={!canMemberUpdate}
            className={peopleSelectClass}
          >
            {(["active", "suspended"] as const).map((state) => (
              <option key={state} value={state}>
                {t(state)}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="member-job-title">{t("jobTitle")}</Label>
        <Select
          id="member-job-title"
          name="jobTitle"
          defaultValue={member.job_title_id ?? ""}
          disabled={!canMemberUpdate}
          className={peopleSelectClass}
        >
          <option value="">{c("notAssigned")}</option>
          {jobTitles.map((title) => (
            <option key={title.job_title_id} value={title.job_title_id}>
              {title.name}
            </option>
          ))}
        </Select>
      </div>
      {canAssign ? (
        <>
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">{c("teams")}</legend>
            <SearchableMultiSelect
              inline
              name="teams"
              label={c("teams")}
              searchLabel={t("searchTeams")}
              selected={teamIds}
              options={teamOptions}
              onChange={setTeamIds}
              emptyHint={t("selectTeams")}
              closeLabel={t("close")}
            />
          </fieldset>
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">{t("teamLeads")}</legend>
            <SearchableMultiSelect
              inline
              name="teamLeads"
              label={t("teamLeads")}
              searchLabel={t("searchTeams")}
              selected={leadIds.filter((id) => teamIds.includes(id))}
              options={teamOptions.filter((option) => teamIds.includes(option.value))}
              onChange={setLeadIds}
              emptyHint={t("teamLeadsHint")}
              closeLabel={t("close")}
            />
          </fieldset>
        </>
      ) : null}
    </>
  );
}

export function BulkMembersDialog({
  open,
  members,
  context,
  roles,
  jobTitles,
  csrfToken,
  onClose,
}: SharedProps & {
  open: boolean;
  members: readonly CorporateMember[];
  onClose: () => void;
}) {
  const t = useTranslations("people");
  const c = useTranslations("corporate");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const authorizationRevision = context.organization.authorization_revision;
  const canMemberUpdate = context.capabilities.includes("member.update");
  const canAssign = context.capabilities.includes("member.manage");
  const [teamId, setTeamId] = useState("");

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={t("editMembers", { count: members.length })}
      description={t("bulkEditBody")}
      closeLabel={t("close")}
      cancelLabel={c("cancel")}
      submitLabel={c("update")}
      busyLabel={c("saving")}
      busy={busy}
      error={error}
      onSubmit={(event) => {
        setError(null);
        const data = new FormData(event.currentTarget);
        const role = fieldValue(data, "role");
        const jobTitle = fieldValue(data, "jobTitle");
        startTransition(async () => {
          let failed = 0;
          for (const member of members) {
            failed += await applyBulkChange(member, {
              role,
              jobTitle,
              teamId: canAssign ? teamId : "",
              context,
              csrfToken,
              authorizationRevision,
              canMemberUpdate,
            });
          }
          if (failed) {
            setError(t("editPartial", { count: failed }));
            router.refresh();
            return;
          }
          onClose();
          router.refresh();
        });
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="bulk-role">{t("role")}</Label>
          <Select
            id="bulk-role"
            name="role"
            defaultValue=""
            disabled={!canMemberUpdate}
            className={peopleSelectClass}
          >
            <option value="">{t("keepUnchanged")}</option>
            {roles.map((role) => (
              <option key={role.name} value={role.name}>
                {role.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="bulk-job-title">{t("jobTitle")}</Label>
          <Select
            id="bulk-job-title"
            name="jobTitle"
            defaultValue=""
            disabled={!canMemberUpdate}
            className={peopleSelectClass}
          >
            <option value="">{t("keepUnchanged")}</option>
            <option value="__none__">{c("notAssigned")}</option>
            {jobTitles.map((title) => (
              <option key={title.job_title_id} value={title.job_title_id}>
                {title.name}
              </option>
            ))}
          </Select>
        </div>
      </div>
      {canAssign ? (
        <div className="space-y-1.5">
          <Label htmlFor="bulk-team">{t("addToTeam")}</Label>
          <Select
            id="bulk-team"
            name="team"
            value={teamId}
            onChange={(event) => {
              setTeamId(event.target.value);
            }}
            className={peopleSelectClass}
          >
            <option value="">{t("keepUnchanged")}</option>
            {context.teams.map((team) => (
              <option key={team.team_id} value={team.team_id}>
                {team.name}
              </option>
            ))}
          </Select>
        </div>
      ) : null}
    </FormDialog>
  );
}
