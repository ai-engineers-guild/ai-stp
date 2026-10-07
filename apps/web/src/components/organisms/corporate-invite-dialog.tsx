"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/atoms/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/atoms/dialog";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { MemberImportFields } from "@/components/molecules/member-import-fields";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { Select } from "@/components/atoms/select";
import { type MemberImportRow, type ImportedMember } from "@/lib/member-import";
import { CopyValue } from "@/components/molecules/copy-value";
import { downloadInvitationLinks, type InvitationLinkRow } from "@/lib/member-export";
import type { CorporateInvitation } from "@/lib/api/generated/types.gen";
import { Icon } from "@/theme";

export type InviteOptions = { role: string; teamIds: string[]; ttlSeconds: number };

/** Protected focus for the invitation's recipient, role, memberships and expiry. */
export function CorporateInviteDialog({
  open,
  onOpenChange,
  busy,
  error,
  roles,
  grantableRoles = roles,
  teams,
  submit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy: boolean;
  error: string | null;
  roles: readonly string[];
  grantableRoles?: readonly string[] | null | undefined;
  teams: readonly { value: string; label: string }[];
  submit: (rows: ImportedMember[], options: InviteOptions) => void;
}) {
  const t = useTranslations("people");
  const [bulk, setBulk] = useState(false);
  const [selectedTeams, setSelectedTeams] = useState<string[]>([]);
  const [parsed, setParsed] = useState<MemberImportRow[]>([]);
  const [helpOpen, setHelpOpen] = useState(false);
  const [role, setRole] = useState("");
  const [ttl, setTtl] = useState("7");
  const ready = parsed.filter((row) => row.error === null);
  const allowedRoles = roles.filter((name) => grantableRoles?.includes(name));
  const roleHint =
    grantableRoles === null
      ? t("rolesUnavailable")
      : !allowedRoles.length
        ? t("noGrantableRoles")
        : allowedRoles.length < roles.length
          ? t("roleGrantHint")
          : undefined;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
    >
      <DialogContent
        closeLabel={t("close")}
        className={`bg-card max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] ${bulk ? "max-w-3xl" : "max-w-[460px]"} gap-5 overflow-y-auto p-6`}
      >
        <div className="space-y-2 pr-6">
          <DialogTitle className="text-2xl leading-tight">
            {t(bulk ? "importFromFile" : "inviteMember")}
          </DialogTitle>
          <DialogDescription className="leading-relaxed">
            {t(bulk ? "bulkInviteBody" : "inviteBody")}
          </DialogDescription>
        </div>
        <form
          className="min-w-0 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            const email = field(data, "email");
            const rows = bulk
              ? ready.map(({ email, displayName }) => ({ email, displayName }))
              : [
                  {
                    email,
                    displayName:
                      field(data, "displayName") || email.split("@")[0]?.slice(0, 80) || email,
                  },
                ];
            const selectedRole = field(data, "role");
            if (busy || !rows.length || !allowedRoles.includes(selectedRole)) return;
            submit(rows, {
              role: selectedRole,
              teamIds: selectedTeams,
              ttlSeconds: Number(data.get("ttl")) * 86400,
            });
          }}
        >
          {bulk ? (
            <MemberImportFields rows={parsed} onRows={setParsed} busy={busy} />
          ) : (
            <InviteRecipientFields busy={busy} />
          )}
          <InviteAccessFields
            busy={busy}
            roles={roles}
            allowedRoles={allowedRoles}
            roleHint={roleHint}
            role={role}
            setRole={setRole}
            ttl={ttl}
            setTtl={setTtl}
            teams={teams}
            selectedTeams={selectedTeams}
            setSelectedTeams={setSelectedTeams}
          />
          {error ? (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Button
              type="submit"
              disabled={busy || !allowedRoles.includes(role) || (bulk && !ready.length)}
              className="h-11 flex-1"
            >
              <Icon
                name={busy ? "loader" : "send"}
                size="sm"
                className={busy ? "animate-spin" : ""}
              />
              {t(busy ? "sending" : bulk ? "sendInvitations" : "sendInvitation")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              className="h-11 flex-1 border-l"
              onClick={() => {
                setBulk(!bulk);
              }}
            >
              <Icon name={bulk ? "user" : "upload"} size="sm" />
              {t(bulk ? "singleInvite" : "importFromFile")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-11"
              disabled={busy}
              title={t("importHelp")}
              aria-label={t("importHelp")}
              onClick={() => {
                setHelpOpen(true);
              }}
            >
              <Icon name="help" size="sm" />
            </Button>
          </div>
        </form>
        <ImportHelp open={helpOpen} onOpenChange={setHelpOpen} />
      </DialogContent>
    </Dialog>
  );
}

function ImportHelp({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("people");
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        closeLabel={t("close")}
        className="max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] overflow-y-auto"
      >
        <DialogTitle>{t("importHelp")}</DialogTitle>
        <DialogDescription>{t("importFileHint")}</DialogDescription>
        <p className="text-sm leading-relaxed">{t("importHelpBody")}</p>
        <pre className="bg-muted overflow-x-auto rounded-sm p-3 text-sm">
          {"email,display_name\nalex@example.com,Alex Morgan\nmaya@example.com,Maya Chen"}
        </pre>
        <p className="text-muted-foreground text-sm leading-relaxed">{t("importHelpValidation")}</p>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            onOpenChange(false);
          }}
        >
          {t("close")}
        </Button>
      </DialogContent>
    </Dialog>
  );
}

function field(data: FormData, name: string) {
  const value = data.get(name);
  return typeof value === "string" ? value.trim() : "";
}
function InviteRecipientFields({ busy }: { busy: boolean }) {
  const t = useTranslations("people");
  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="invite-email">
          {t("email")}{" "}
          <span aria-hidden className="text-primary">
            *
          </span>
        </Label>
        <Input
          id="invite-email"
          name="email"
          type="email"
          maxLength={320}
          required
          autoComplete="email"
          placeholder={t("emailPlaceholder")}
          disabled={busy}
          className="h-10"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="invite-display-name">{t("displayNameOptional")}</Label>
        <Input
          id="invite-display-name"
          name="displayName"
          maxLength={80}
          autoComplete="name"
          placeholder={t("namePlaceholder")}
          disabled={busy}
          className="h-10"
        />
      </div>
    </>
  );
}
function InviteAccessFields({
  busy,
  roles,
  allowedRoles,
  roleHint,
  teams,
  selectedTeams,
  setSelectedTeams,
  role,
  setRole,
  ttl,
  setTtl,
}: {
  busy: boolean;
  roles: readonly string[];
  allowedRoles: readonly string[];
  roleHint: string | undefined;
  role: string;
  setRole: (value: string) => void;
  ttl: string;
  setTtl: (value: string) => void;
  teams: readonly { value: string; label: string }[];
  selectedTeams: string[];
  setSelectedTeams: (value: string[]) => void;
}) {
  const t = useTranslations("people");
  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="invite-role">
          {t("role")}{" "}
          <span aria-hidden className="text-primary">
            *
          </span>
        </Label>
        <Select
          id="invite-role"
          name="role"
          required
          value={allowedRoles.includes(role) ? role : ""}
          aria-describedby={roleHint ? "invite-role-hint" : undefined}
          onChange={(event) => {
            setRole(event.target.value);
          }}
          disabled={busy}
        >
          <option value="" disabled>
            {t("selectRole")}
          </option>
          {roles.map((role) => (
            <option key={role} value={role} disabled={!allowedRoles.includes(role)}>
              {allowedRoles.includes(role) ? role : `${role} — ${t("roleUnavailable")}`}
            </option>
          ))}
        </Select>
        {roleHint ? (
          <p
            id="invite-role-hint"
            role={!allowedRoles.length ? "alert" : undefined}
            className="text-muted-foreground text-sm leading-relaxed"
          >
            {roleHint}
          </p>
        ) : null}
      </div>
      <fieldset disabled={busy} className="space-y-1.5">
        <Label>{t("teamsOptional")}</Label>
        <SearchableMultiSelect
          inline
          name="team_ids"
          label={t("teamsOptional")}
          searchLabel={t("searchTeams")}
          selected={selectedTeams}
          options={teams}
          onChange={setSelectedTeams}
          emptyHint={t("selectTeams")}
          closeLabel={t("close")}
        />
      </fieldset>
      <div className="space-y-1.5">
        <Label htmlFor="invite-ttl">
          {t("expiresIn")}{" "}
          <span aria-hidden className="text-primary">
            *
          </span>
        </Label>
        <Select
          id="invite-ttl"
          name="ttl"
          required
          value={ttl}
          onChange={(event) => {
            setTtl(event.target.value);
          }}
          disabled={busy}
        >
          {[1, 3, 7, 14, 30].map((days) => (
            <option key={days} value={days}>
              {t("days", { days })}
            </option>
          ))}
        </Select>
      </div>
    </>
  );
}
export function InvitationReceipts({
  rows,
  close,
}: {
  rows: InvitationLinkRow[];
  close: () => void;
}) {
  const t = useTranslations("people");
  return (
    <Dialog
      open={rows.length > 0}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent
        closeLabel={t("close")}
        className="max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] overflow-y-auto"
      >
        <DialogTitle>{t("invitationsSent")}</DialogTitle>
        <DialogDescription>{t("receiptBody")}</DialogDescription>
        {rows.map((row) => (
          <div key={row.email} className="min-w-0 space-y-2">
            <p className="text-sm">
              {row.displayName} <span className="text-muted-foreground">{row.email}</span>
            </p>
            <CopyValue
              value={row.link}
              label={t("copyLink")}
              copied={t("copied")}
              failed={t("copyFailed")}
            />
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            downloadInvitationLinks(rows, "csv");
          }}
        >
          <Icon name="download" size="sm" />
          {t("downloadCsv")}
        </Button>
      </DialogContent>
    </Dialog>
  );
}

export function RevokeInvitationDialog({
  revoke,
  busy,
  error,
  setRevoke,
  confirm,
}: {
  revoke: CorporateInvitation | null;
  busy: boolean;
  error: string | null;
  setRevoke: (value: CorporateInvitation | null) => void;
  confirm: () => void;
}) {
  const t = useTranslations("people");
  return (
    <Dialog
      open={Boolean(revoke)}
      onOpenChange={(next) => {
        if (!next && !busy) setRevoke(null);
      }}
    >
      <DialogContent closeLabel={t("close")} className="w-[calc(100%-2rem)]">
        <DialogTitle>{t("revokeInvitation")}</DialogTitle>
        <DialogDescription>
          {t("revokeBody", { email: revoke?.recipient_email ?? "" })}
        </DialogDescription>
        {error ? (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        ) : null}
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setRevoke(null);
            }}
          >
            {t("cancel")}
          </Button>
          <Button type="button" variant="destructive" disabled={busy} onClick={confirm}>
            {t(busy ? "revoking" : "revokeInvitation")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
