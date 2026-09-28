/* eslint-disable max-lines, max-lines-per-function, @typescript-eslint/no-confusing-void-expression */
"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";

import { corporateMutationAction } from "@/actions/corporate";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Switch } from "@/components/atoms/switch";
import { Textarea } from "@/components/atoms/textarea";
import { CopyValue } from "@/components/molecules/copy-value";
import type {
  CorporateInvitation,
  CorporateMember,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";
import { downloadInvitationLinks, EXPORT_FORMATS, type ExportFormat } from "@/lib/member-export";
import { parseMemberImport, type ImportedMember } from "@/lib/member-import";

type GeneratedLink = { displayName: string; email: string; link: string };

const INVITATION_STATE_VARIANT = {
  pending: "secondary",
  accepted: "success",
  expired: "warning",
  revoked: "destructive",
} as const;

const MAIL_STATE_VARIANT = {
  queued: "secondary",
  sent: "success",
  failed: "destructive",
} as const;

const selectClass =
  "border-input bg-background ring-offset-background focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none";

const field = (formData: FormData, name: string) => {
  const value = formData.get(name);
  return typeof value === "string" ? value.trim() : "";
};

export function CorporateMembersPanel({
  csrfToken,
  organizationId,
  authorizationRevision,
  locale,
  members,
  roles,
  invitations,
  allowedDomains,
  canInvite,
  canManagePolicy,
  labels,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  locale: string;
  members: CorporateMember[];
  roles: CorporateRoleView[];
  invitations: CorporateInvitation[];
  allowedDomains: string[];
  canInvite: boolean;
  canManagePolicy: boolean;
  labels: {
    members: string;
    noMembers: string;
    inviteTitle: string;
    inviteBody: string;
    email: string;
    displayName: string;
    role: string;
    expiresInDays: string;
    create: string;
    invite: string;
    creating: string;
    invitations: string;
    noInvitations: string;
    expiresAt: string;
    revoke: string;
    revoking: string;
    invitationLinks: string;
    copy: string;
    copyAll: string;
    copied: string;
    bulkImport: string;
    bulkImportBody: string;
    importFile: string;
    importText: string;
    importPlaceholder: string;
    parse: string;
    parsedCount: string;
    inviteAll: string;
    bulkProgress: string;
    bulkFailed: string;
    domainPolicy: string;
    domainPolicyBody: string;
    domainRestrict: string;
    domains: string;
    domainsPlaceholder: string;
    domainsHint: string;
    save: string;
    saving: string;
    saved: string;
    failed: string;
    exportFormat: string;
    download: string;
    mail: string;
    mailQueued: string;
    mailSent: string;
    mailFailed: string;
  };
}) {
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const report = (text: string, error = false) => setMessage({ text, error });
  const [links, setLinks] = useState<GeneratedLink[]>([]);
  const [exportFormat, setExportFormat] = useState<ExportFormat>("csv");
  const [parsed, setParsed] = useState<ImportedMember[]>([]);
  const [importText, setImportText] = useState("");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const roleNames = [...new Set(roles.map((role) => role.name))];
  const bulkRole = roleNames[0] ?? "staff";

  function linkFor(invitation: CorporateInvitation): GeneratedLink | null {
    if (!invitation.token || typeof window === "undefined") return null;
    return {
      displayName: invitation.display_name,
      email: invitation.recipient_email,
      link: `${window.location.origin}/${locale}/corporate-invitations/${invitation.invitation_id}#token=${invitation.token}`,
    };
  }

  function createInvitations(
    rows: ImportedMember[],
    role: string,
    ttlSeconds?: number,
    reset?: () => void,
  ) {
    if (!rows.length || !role) {
      report(labels.failed, true);
      return;
    }
    setMessage(null);
    setProgress({ done: 0, total: rows.length });
    startTransition(async () => {
      const generated: GeneratedLink[] = [];
      for (const [index, row] of rows.entries()) {
        const result = await corporateMutationAction({
          csrfToken,
          organizationId,
          method: "POST",
          path: `/v1/corporate/organizations/${organizationId}/invitations`,
          body: {
            schema_version: 1,
            recipient_email: row.email,
            display_name: row.displayName,
            role,
            ...(ttlSeconds ? { ttl_seconds: ttlSeconds } : {}),
            authorization_revision: authorizationRevision,
            idempotency_key: crypto.randomUUID(),
          },
        });
        if (!result.ok) {
          report(`${row.email}: ${result.message}`, true);
          setProgress({ done: index, total: rows.length });
          setLinks((current) => [...generated, ...current]);
          router.refresh();
          return;
        }
        const link = linkFor(result.data as CorporateInvitation);
        if (link) generated.push(link);
        setProgress({ done: index + 1, total: rows.length });
      }
      setLinks((current) => [...generated, ...current]);
      setProgress(null);
      report(labels.saved);
      reset?.();
      router.refresh();
    });
  }

  function revokeInvitation(invitationId: string) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        method: "POST",
        path: `/v1/corporate/organizations/${organizationId}/invitations/${invitationId}/revoke`,
        body: {
          schema_version: 1,
          authorization_revision: authorizationRevision,
          idempotency_key: crypto.randomUUID(),
        },
      });
      report(result.ok ? labels.saved : result.message, !result.ok);
      if (result.ok) router.refresh();
    });
  }

  function savePolicy(form: HTMLFormElement) {
    const formData = new FormData(form);
    const restricted = formData.get("domainRestrict") === "true";
    const domains = restricted
      ? field(formData, "domains")
          .split(/[\s,]+/)
          .map((domain) => domain.trim().toLowerCase())
          .filter(Boolean)
      : [];
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        method: "PUT",
        path: `/v1/corporate/organizations/${organizationId}/membership/policy`,
        body: {
          schema_version: 1,
          authorization_revision: authorizationRevision,
          allowed_email_domains: domains,
          idempotency_key: crypto.randomUUID(),
        },
      });
      report(result.ok ? labels.saved : result.message, !result.ok);
      if (result.ok) router.refresh();
    });
  }

  return (
    <section className="border-border bg-card rounded-lg border p-5 shadow-sm sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-medium">{labels.members}</h2>
        <Badge variant="secondary">{members.length}</Badge>
      </div>

      <div aria-live="polite" className="mt-3 min-h-5">
        {message ? (
          <p
            role={message.error ? "alert" : undefined}
            className={
              message.error
                ? "text-destructive text-sm font-medium"
                : "text-muted-foreground text-sm"
            }
          >
            {message.text}
          </p>
        ) : null}
      </div>

      {members.length ? (
        <ul className="mt-2 space-y-2">
          {members.map((member) => (
            <li
              key={member.account_id}
              className="border-border flex flex-wrap items-center justify-between gap-2 rounded border p-3"
            >
              <div className="min-w-0">
                <p className="truncate font-medium">{member.display_name ?? member.account_id}</p>
                {member.job_title_name ? (
                  <p className="text-muted-foreground truncate text-sm">{member.job_title_name}</p>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Badge variant="outline">{member.role}</Badge>
                <Badge variant={member.state === "active" ? "success" : "secondary"}>
                  {member.state}
                </Badge>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground mt-2 text-sm">{labels.noMembers}</p>
      )}

      {canInvite ? (
        <div className="border-border mt-6 space-y-8 border-t pt-6">
          <div>
            <h3 className="font-medium">{labels.inviteTitle}</h3>
            <p className="text-muted-foreground mt-1 text-sm">{labels.inviteBody}</p>
            <form
              className="mt-4 grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-5"
              onSubmit={(event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const formData = new FormData(form);
                const ttlDays = Number.parseInt(field(formData, "ttlDays"), 10);
                createInvitations(
                  [
                    {
                      displayName: field(formData, "displayName") || field(formData, "email"),
                      email: field(formData, "email"),
                    },
                  ],
                  field(formData, "role"),
                  Number.isFinite(ttlDays) && ttlDays > 0 ? ttlDays * 86400 : undefined,
                  () => form.reset(),
                );
              }}
            >
              <div className="space-y-1.5">
                <Label htmlFor="invite-email">{labels.email}</Label>
                <Input id="invite-email" name="email" type="email" required autoComplete="off" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invite-display-name">{labels.displayName}</Label>
                <Input id="invite-display-name" name="displayName" required autoComplete="off" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invite-role">{labels.role}</Label>
                <select id="invite-role" name="role" required className={selectClass}>
                  {roleNames.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invite-ttl">{labels.expiresInDays}</Label>
                <Input id="invite-ttl" name="ttlDays" type="number" min={1} placeholder="1" />
              </div>
              <Button type="submit" disabled={busy}>
                {busy ? labels.creating : labels.invite}
              </Button>
            </form>
          </div>

          <div>
            <h3 className="font-medium">{labels.bulkImport}</h3>
            <p className="text-muted-foreground mt-1 text-sm">{labels.bulkImportBody}</p>
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="import-file">{labels.importFile}</Label>
                <Input
                  id="import-file"
                  ref={fileRef}
                  type="file"
                  accept=".csv,.md,.markdown,.json,.xml,.html,.htm,.txt,text/*,application/json,application/xml"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    void file
                      .text()
                      .then((text) => {
                        setImportText(text);
                        setParsed(parseMemberImport(text, file.name));
                      })
                      .catch(() => report(labels.failed, true));
                  }}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="import-text">{labels.importText}</Label>
                <Textarea
                  id="import-text"
                  value={importText}
                  placeholder={labels.importPlaceholder}
                  rows={4}
                  onChange={(event) => setImportText(event.target.value)}
                />
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={!importText.trim()}
                onClick={() => {
                  const result = parseMemberImport(importText);
                  setParsed(result);
                  report(
                    result.length
                      ? labels.parsedCount.replace("{count}", String(result.length))
                      : labels.failed,
                    !result.length,
                  );
                }}
              >
                {labels.parse}
              </Button>
              <Button
                type="button"
                disabled={busy || !parsed.length}
                onClick={() =>
                  createInvitations(parsed, bulkRole, undefined, () => {
                    setParsed([]);
                    setImportText("");
                    if (fileRef.current) fileRef.current.value = "";
                  })
                }
              >
                {labels.inviteAll} ({parsed.length})
              </Button>
              {progress ? (
                <Badge variant="secondary">
                  {labels.bulkProgress
                    .replace("{done}", String(progress.done))
                    .replace("{total}", String(progress.total))}
                </Badge>
              ) : null}
            </div>
            {parsed.length ? (
              <ul className="border-border mt-3 max-h-40 space-y-1 overflow-y-auto rounded border p-3 text-sm">
                {parsed.map((member) => (
                  <li key={member.email} className="flex flex-wrap gap-x-2">
                    <span className="font-medium">{member.displayName}</span>
                    <span className="text-muted-foreground">{member.email}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          {links.length ? (
            <div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="flex items-center gap-2 font-medium">
                  {labels.invitationLinks}
                  <Badge variant="secondary">{links.length}</Badge>
                </h3>
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      void navigator.clipboard.writeText(links.map((link) => link.link).join("\n"));
                    }}
                  >
                    {labels.copyAll}
                  </Button>
                  <Label htmlFor="export-format" className="sr-only">
                    {labels.exportFormat}
                  </Label>
                  <select
                    id="export-format"
                    value={exportFormat}
                    aria-label={labels.exportFormat}
                    className="border-input bg-background ring-offset-background focus-visible:ring-ring flex h-9 rounded-md border px-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
                    onChange={(event) => setExportFormat(event.target.value as ExportFormat)}
                  >
                    {EXPORT_FORMATS.map((format) => (
                      <option key={format} value={format}>
                        {format.toUpperCase()}
                      </option>
                    ))}
                  </select>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => downloadInvitationLinks(links, exportFormat)}
                  >
                    {labels.download}
                  </Button>
                </div>
              </div>
              <ul className="mt-3 space-y-2">
                {links.map((link) => (
                  <li
                    key={link.link}
                    className="border-border flex flex-wrap items-center justify-between gap-3 rounded border p-3"
                  >
                    <div className="w-full min-w-0 sm:w-52">
                      <p className="truncate text-sm font-medium">{link.displayName}</p>
                      <p className="text-muted-foreground truncate text-sm">{link.email}</p>
                    </div>
                    <div className="min-w-0 flex-1">
                      <CopyValue value={link.link} label={labels.copy} copied={labels.copied} />
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="border-border mt-6 border-t pt-6">
        <h3 className="font-medium">{labels.invitations}</h3>
        {invitations.length ? (
          <ul className="mt-3 space-y-2">
            {invitations.map((invitation) => (
              <li
                key={invitation.invitation_id}
                className="border-border flex flex-wrap items-center justify-between gap-3 rounded border p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {invitation.display_name}
                    <span className="text-muted-foreground font-normal">
                      {" "}
                      · {invitation.recipient_email}
                    </span>
                  </p>
                  <p className="text-muted-foreground text-sm">
                    {invitation.role} · {labels.expiresAt} {invitation.expires_at.slice(0, 10)}
                  </p>
                  {invitation.delivery_error ? (
                    <p className="text-destructive text-xs">
                      {labels.mail}: {invitation.delivery_error}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge variant={INVITATION_STATE_VARIANT[invitation.state]}>
                    {invitation.state}
                  </Badge>
                  {invitation.delivery_state ? (
                    <Badge
                      variant={MAIL_STATE_VARIANT[invitation.delivery_state]}
                      title={invitation.delivery_error ?? undefined}
                    >
                      {labels.mail}{" "}
                      {
                        {
                          queued: labels.mailQueued,
                          sent: labels.mailSent,
                          failed: labels.mailFailed,
                        }[invitation.delivery_state]
                      }
                    </Badge>
                  ) : null}
                  {invitation.state === "pending" ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => revokeInvitation(invitation.invitation_id)}
                    >
                      {busy ? labels.revoking : labels.revoke}
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground mt-3 text-sm">{labels.noInvitations}</p>
        )}
      </div>

      {canManagePolicy ? (
        <div className="border-border mt-6 border-t pt-6">
          <h3 className="font-medium">{labels.domainPolicy}</h3>
          <p className="text-muted-foreground mt-1 text-sm">{labels.domainPolicyBody}</p>
          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              savePolicy(event.currentTarget);
            }}
          >
            <div className="flex items-center gap-3">
              <Switch
                id="domain-restrict"
                name="domainRestrict"
                defaultChecked={allowedDomains.length > 0}
                aria-label={labels.domainRestrict}
              />
              <Label htmlFor="domain-restrict" className="font-normal">
                {labels.domainRestrict}
              </Label>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="domains">{labels.domains}</Label>
              <Input
                id="domains"
                name="domains"
                defaultValue={allowedDomains.join(", ")}
                placeholder={labels.domainsPlaceholder}
                autoComplete="off"
              />
              <p className="text-muted-foreground text-sm">{labels.domainsHint}</p>
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? labels.saving : labels.save}
            </Button>
          </form>
        </div>
      ) : null}
    </section>
  );
}
