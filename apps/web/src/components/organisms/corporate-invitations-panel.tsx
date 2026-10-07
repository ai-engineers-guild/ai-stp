"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import {
  CorporateInviteDialog,
  InvitationReceipts,
  RevokeInvitationDialog,
  type InviteOptions,
} from "@/components/organisms/corporate-invite-dialog";
import {
  PEOPLE_PAGE_SIZE,
  PeopleSearch,
  PeopleSelect,
  usePeopleFilters,
} from "@/components/organisms/corporate-people-ui";
import { PagePager } from "@/components/molecules/page-pager";
import type {
  CorporateContext,
  CorporateInvitation,
  CorporateMember,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";
import { exportInvitationDirectory, type InvitationLinkRow } from "@/lib/member-export";
import type { ImportedMember } from "@/lib/member-import";
import { InvitationTable } from "@/components/organisms/corporate-invitations-table";
import { Icon } from "@/theme";
import { isOutstandingInvitation, invitationDisplayState } from "@/lib/corporate-invitation-state";

export { CorporateMembershipPolicyControls } from "@/components/organisms/corporate-membership-policy-controls";

export { isOutstandingInvitation } from "@/lib/corporate-invitation-state";

type Props = {
  csrfToken: string;
  context: CorporateContext;
  roles: readonly CorporateRoleView[];
  members: readonly CorporateMember[];
  invitations: readonly CorporateInvitation[];
  now: string;
  unavailable?: boolean;
  grantableRoles?: readonly string[] | null;
};

export function CorporateInvitationsPanel({
  csrfToken,
  context,
  roles,
  members,
  invitations,
  now,
  unavailable = false,
  grantableRoles,
}: Props) {
  const t = useTranslations("people");
  const filters = usePeopleFilters();
  const [selected, setSelected] = useState<string[]>([]);
  const {
    busy,
    open,
    setOpen,
    error,
    setError,
    message,
    receipts,
    setReceipts,
    revoke,
    setRevoke,
    create,
    revokeConfirmed,
  } = useInvitationActions(csrfToken, context);
  const inviteRoles = [...new Set([...roles.map((role) => role.name), ...(grantableRoles ?? [])])];
  const stamp = Date.parse(now);
  const canInvite = context.capabilities.includes("member.invite");
  const status = filters.get("status") || "pending";
  const query = filters.get("query").trim().toLowerCase();
  const filtered = invitations
    .filter(
      (row) =>
        (!query || `${row.display_name} ${row.recipient_email}`.toLowerCase().includes(query)) &&
        (!filters.get("role") || row.role === filters.get("role")) &&
        (!filters.get("team") || row.team_ids.includes(filters.get("team"))) &&
        (status === "all" ||
          (status === "pending"
            ? isOutstandingInvitation(row, stamp)
            : invitationDisplayState(row, stamp) === status)),
    )
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  const page = Math.min(
    Math.max(1, Number(filters.get("page")) || 1),
    Math.max(1, Math.ceil(filtered.length / PEOPLE_PAGE_SIZE)),
  );
  const rows = filtered.slice((page - 1) * PEOPLE_PAGE_SIZE, page * PEOPLE_PAGE_SIZE);
  const chosen = filtered.filter((row) => selected.includes(row.invitation_id));
  const exportRows = () => {
    exportInvitationDirectory(chosen.length ? chosen : filtered, context, members, stamp);
  };
  return (
    <section
      aria-label={t("invitations")}
      className="border-border min-w-0 rounded-lg border"
      data-ui="invitations-directory"
    >
      <InvitationToolbar
        filters={filters}
        status={status}
        invitations={invitations}
        context={context}
        exportRows={exportRows}
        canExport={filtered.length > 0}
        canInvite={canInvite}
        invite={() => {
          setError(null);
          setOpen(true);
        }}
      />
      {unavailable ? (
        <p role="alert" className="text-destructive px-4 pb-4 text-sm">
          {t("invitationsUnavailable")}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="text-muted-foreground px-4 pb-3 text-sm">
          {message}
        </p>
      ) : null}
      {chosen.length ? (
        <div className="bg-muted mx-4 mb-3 flex items-center justify-between rounded-sm px-3 py-2 text-sm">
          <span>{t("selected", { count: chosen.length })}</span>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setSelected([]);
            }}
          >
            {t("clearSelection")}
          </Button>
        </div>
      ) : null}
      <div className="border-border border-t px-4">
        <InvitationTable
          rows={rows}
          context={context}
          members={members}
          selected={selected}
          now={stamp}
          canInvite={canInvite}
          revoke={(row) => {
            setError(null);
            setRevoke(row);
          }}
          toggle={(id, checked) => {
            setSelected((current) =>
              checked ? [...current, id] : current.filter((item) => item !== id),
            );
          }}
          selectPage={(checked) => {
            setSelected((current) =>
              checked
                ? [...new Set([...current, ...rows.map((row) => row.invitation_id)])]
                : current.filter((id) => !rows.some((row) => row.invitation_id === id)),
            );
          }}
        />
        <InvitationsPager page={page} filtered={filtered} filters={filters} />
      </div>
      <CorporateInviteDialog
        {...{ open, busy, error }}
        onOpenChange={setOpen}
        roles={inviteRoles}
        grantableRoles={grantableRoles}
        teams={context.teams.map((team) => ({ value: team.team_id, label: team.name }))}
        submit={(rows, options) => {
          void create(rows, options);
        }}
      />
      <InvitationReceipts
        rows={open ? [] : receipts}
        close={() => {
          setReceipts([]);
        }}
      />
      <RevokeInvitationDialog
        revoke={revoke}
        busy={busy}
        error={error}
        setRevoke={setRevoke}
        confirm={() => {
          void revokeConfirmed();
        }}
      />
    </section>
  );
}

function InvitationsPager({
  page,
  filtered,
  filters,
}: {
  page: number;
  filtered: readonly CorporateInvitation[];
  filters: ReturnType<typeof usePeopleFilters>;
}) {
  const t = useTranslations("people");
  return (
    <PagePager
      label={t("pagination")}
      page={page}
      totalPages={Math.max(1, Math.ceil(filtered.length / PEOPLE_PAGE_SIZE))}
      summary={
        <p aria-live="polite" className="text-muted-foreground text-sm tabular-nums">
          {t("showingInvitations", {
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
  );
}

function InvitationToolbar({
  filters,
  status,
  invitations,
  context,
  exportRows,
  canExport,
  canInvite,
  invite,
}: {
  filters: ReturnType<typeof usePeopleFilters>;
  status: string;
  invitations: readonly CorporateInvitation[];
  context: CorporateContext;
  exportRows: () => void;
  canExport: boolean;
  canInvite: boolean;
  invite: () => void;
}) {
  const t = useTranslations("people");
  return (
    <div className="grid grid-cols-2 items-center gap-3 p-4 lg:flex lg:flex-wrap">
      <div className="col-span-2 min-w-0 lg:flex-1">
        <PeopleSearch
          value={filters.get("query")}
          onChange={(value) => {
            filters.update("query", value);
          }}
          label={t("searchInvitations")}
        />
      </div>
      <PeopleSelect
        label={t("allStatuses")}
        value={status}
        options={["pending", "email_confirm_pending", "accepted", "expired", "revoked", "all"].map(
          (state) => ({ value: state, label: t(state === "all" ? "allStatuses" : state) }),
        )}
        onChange={(value) => {
          filters.update("status", value || "all");
        }}
      />
      <PeopleSelect
        label={t("allRoles")}
        value={filters.get("role")}
        options={[...new Set(invitations.map((row) => row.role))].map((role) => ({
          value: role,
          label: role,
        }))}
        onChange={(value) => {
          filters.update("role", value);
        }}
      />
      <PeopleSelect
        label={t("allTeams")}
        value={filters.get("team")}
        options={context.teams.map((team) => ({ value: team.team_id, label: team.name }))}
        onChange={(value) => {
          filters.update("team", value);
        }}
      />
      <Button
        type="button"
        variant="outline"
        className="h-11"
        disabled={!canExport}
        onClick={exportRows}
      >
        <Icon name="download" size="sm" />
        {t("downloadCsv")}
      </Button>
      {canInvite ? (
        <Button type="button" className="col-span-2 h-11" onClick={invite}>
          <Icon name="plus" size="sm" />
          {t("inviteMember")}
        </Button>
      ) : null}
    </div>
  );
}

function useInvitationActions(csrfToken: string, context: CorporateContext) {
  const t = useTranslations("people");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [receipts, setReceipts] = useState<InvitationLinkRow[]>([]);
  const [revoke, setRevoke] = useState<CorporateInvitation | null>(null);
  const retries = useRef(new Map<string, string>());
  function keyFor(effect: unknown) {
    const fingerprint = JSON.stringify(effect);
    let key = retries.current.get(fingerprint);
    if (!key) {
      key = crypto.randomUUID();
      retries.current.set(fingerprint, key);
    }
    return key;
  }
  async function create(rowsToInvite: ImportedMember[], options: InviteOptions) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const generated: InvitationLinkRow[] = [];
    try {
      for (const row of rowsToInvite) {
        const effect = {
          recipient_email: row.email,
          display_name: row.displayName,
          role: options.role,
          team_ids: options.teamIds,
          ttl_seconds: options.ttlSeconds,
          authorization_revision: context.organization.authorization_revision,
        };
        const result = await corporateMutationAction({
          csrfToken,
          organizationId: context.organization.organization_id,
          method: "POST",
          path: `/v1/corporate/organizations/${context.organization.organization_id}/invitations`,
          body: { schema_version: 1, ...effect, idempotency_key: keyFor(effect) },
        });
        if (!result.ok) {
          setError(
            `${row.email}: ${result.code === "AI_STP_PERMISSION_DENIED" ? t("invitationGrantDenied") : result.message}`,
          );
          if (generated.length) router.refresh();
          return;
        }
        const created = result.data as CorporateInvitation;
        if (created.token)
          generated.push({
            ...row,
            link: `${window.location.origin}/${document.documentElement.lang}/corporate-invitations/${created.invitation_id}#token=${created.token}`,
          });
      }
      setOpen(false);
      setMessage(t("invitationsSent"));
      router.refresh();
    } catch {
      setError(t("invitationRequestFailed"));
    } finally {
      if (generated.length)
        setReceipts((current) => [
          ...new Map([...current, ...generated].map((item) => [item.email, item])).values(),
        ]);
      inFlight.current = false;
      setBusy(false);
    }
  }
  async function revokeConfirmed() {
    if (!revoke || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const effect = {
        authorization_revision: context.organization.authorization_revision,
        invitation_id: revoke.invitation_id,
      };
      const result = await corporateMutationAction({
        csrfToken,
        organizationId: context.organization.organization_id,
        method: "POST",
        path: `/v1/corporate/organizations/${context.organization.organization_id}/invitations/${revoke.invitation_id}/revoke`,
        body: {
          schema_version: 1,
          authorization_revision: effect.authorization_revision,
          idempotency_key: keyFor(effect),
        },
      });
      if (!result.ok) {
        setError(result.message);
        return;
      }
      setRevoke(null);
      setMessage(t("invitationRevoked"));
      router.refresh();
    } catch {
      setError(t("invitationRequestFailed"));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return {
    busy,
    open,
    setOpen,
    error,
    setError,
    message,
    receipts,
    setReceipts,
    revoke,
    setRevoke,
    create,
    revokeConfirmed,
  };
}
