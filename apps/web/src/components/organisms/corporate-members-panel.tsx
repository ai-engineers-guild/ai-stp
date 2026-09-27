"use client";

/* eslint-disable max-lines, @typescript-eslint/no-confusing-void-expression */

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { parseMemberImport, type ImportedMember } from "@/lib/member-import";

import type {
  CorporateInvitation,
  CorporateMember,
  CorporateRoleView,
} from "@/lib/api/generated/types.gen";

type GeneratedLink = { email: string; link: string };

type Labels = {
  members: string;
  noMembers: string;
  invite: string;
  inviteTitle: string;
  inviteBody: string;
  email: string;
  displayName: string;
  role: string;
  expiresInDays: string;
  create: string;
  creating: string;
  invitations: string;
  noInvitations: string;
  state: string;
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
};

type Props = {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  locale: string;
  members: readonly CorporateMember[];
  roles: readonly CorporateRoleView[];
  invitations: readonly CorporateInvitation[];
  allowedDomains: readonly string[];
  canInvite: boolean;
  canManagePolicy: boolean;
  labels: Labels;
};

function roleNames(roles: readonly CorporateRoleView[]): string[] {
  const names = roles.map((role) => role.name);
  return names.length ? names : ["staff"];
}

// eslint-disable-next-line max-lines-per-function
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
}: Props) {
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const availableRoles = roleNames(roles);

  const [invite, setInvite] = useState({
    email: "",
    displayName: "",
    role: availableRoles[0] ?? "staff",
  });
  const [bulkRole, setBulkRole] = useState(availableRoles[0] ?? "staff");
  const [parsed, setParsed] = useState<ImportedMember[]>([]);
  const [importText, setImportText] = useState("");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [links, setLinks] = useState<GeneratedLink[]>([]);
  const [restricted, setRestricted] = useState(allowedDomains.length > 0);
  const [domains, setDomains] = useState(allowedDomains.join(", "));
  const fileRef = useRef<HTMLInputElement>(null);

  function invitationLink(invitation: CorporateInvitation): string | null {
    if (!invitation.token || typeof window === "undefined") return null;
    return `${window.location.origin}/${locale}/corporate-invitations/${invitation.invitation_id}#token=${invitation.token}`;
  }

  function copyText(value: string) {
    void navigator.clipboard.writeText(value).catch(() => undefined);
  }

  function submit(method: "POST" | "PUT", path: string, body: unknown, after?: () => void) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        path,
        method,
        body,
      });
      setMessage(result.ok ? labels.saved : result.message);
      if (result.ok) {
        after?.();
        router.refresh();
      }
    });
  }

  function createInvitations(rows: ImportedMember[], role: string) {
    setMessage(null);
    setLinks([]);
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
            authorization_revision: authorizationRevision,
            idempotency_key: crypto.randomUUID(),
          },
        });
        if (!result.ok) {
          setMessage(`${row.email}: ${result.message}`);
          setProgress({ done: index, total: rows.length });
          setLinks(generated);
          return;
        }
        const invitation = result.data as CorporateInvitation;
        const link = invitationLink(invitation);
        if (link) generated.push({ email: row.email, link });
        setProgress({ done: index + 1, total: rows.length });
      }
      setLinks(generated);
      setMessage(labels.saved);
      router.refresh();
    });
  }

  async function parseFile(file: File) {
    setParsed(parseMemberImport(await file.text(), file.name));
  }

  return (
    <section className="border-border bg-card space-y-8 rounded-lg border p-5 shadow-sm sm:p-6">
      {canInvite ? (
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={(event) => {
            event.preventDefault();
            createInvitations(
              [{ displayName: invite.displayName || invite.email, email: invite.email }],
              invite.role,
            );
          }}
        >
          <h2 className="font-medium sm:col-span-2 lg:col-span-5">{labels.inviteTitle}</h2>
          <div>
            <Label htmlFor="corporate-invite-email">{labels.email}</Label>
            <Input
              id="corporate-invite-email"
              type="email"
              required
              value={invite.email}
              onChange={(event) => setInvite({ ...invite, email: event.target.value })}
            />
          </div>
          <div>
            <Label htmlFor="corporate-invite-name">{labels.displayName}</Label>
            <Input
              id="corporate-invite-name"
              value={invite.displayName}
              maxLength={80}
              onChange={(event) => setInvite({ ...invite, displayName: event.target.value })}
            />
          </div>
          <SelectField
            id="corporate-invite-role"
            label={labels.role}
            value={invite.role}
            onChange={(role) => setInvite({ ...invite, role })}
            options={availableRoles.map((role) => ({ value: role, label: role }))}
          />
          <Button type="submit" disabled={busy} className="self-end">
            {busy ? labels.creating : labels.invite}
          </Button>
        </form>
      ) : null}

      {canInvite ? (
        <div className="border-border space-y-4 border-t pt-6">
          <div className="space-y-1">
            <h2 className="font-medium">{labels.bulkImport}</h2>
            <p className="text-muted-foreground text-sm">{labels.bulkImportBody}</p>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="corporate-import-file">{labels.importFile}</Label>
              <Input
                id="corporate-import-file"
                ref={fileRef}
                type="file"
                accept=".csv,.txt,.md,.markdown,.json,.xml,.html,.htm"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void parseFile(file);
                }}
              />
              <Label htmlFor="corporate-import-text">{labels.importText}</Label>
              <Textarea
                id="corporate-import-text"
                rows={5}
                value={importText}
                placeholder={labels.importPlaceholder}
                onChange={(event) => setImportText(event.target.value)}
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy || !importText.trim()}
                  onClick={() => setParsed(parseMemberImport(importText))}
                >
                  {labels.parse}
                </Button>
                <SelectField
                  id="corporate-bulk-role"
                  label={labels.role}
                  value={bulkRole}
                  onChange={setBulkRole}
                  options={availableRoles.map((role) => ({ value: role, label: role }))}
                />
              </div>
            </div>
            <div className="space-y-2">
              {parsed.length ? (
                <>
                  <p className="text-muted-foreground text-sm" role="status">
                    {labels.parsedCount.replace("{count}", String(parsed.length))}
                  </p>
                  <ul className="border-border max-h-56 space-y-1 overflow-y-auto rounded border p-3 text-sm">
                    {parsed.map((row) => (
                      <li key={row.email} className="flex justify-between gap-3">
                        <span className="truncate">{row.displayName}</span>
                        <span className="text-muted-foreground truncate">{row.email}</span>
                      </li>
                    ))}
                  </ul>
                  <Button
                    type="button"
                    disabled={busy}
                    onClick={() => createInvitations(parsed, bulkRole)}
                  >
                    {busy ? labels.creating : labels.inviteAll}
                  </Button>
                </>
              ) : null}
            </div>
          </div>
          {progress ? (
            <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
              {labels.bulkProgress
                .replace("{done}", String(progress.done))
                .replace("{total}", String(progress.total))}
            </p>
          ) : null}
        </div>
      ) : null}

      {links.length ? (
        <div className="border-border space-y-3 border-t pt-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-medium">{labels.invitationLinks}</h2>
            <Button
              type="button"
              variant="outline"
              onClick={() => copyText(links.map((item) => item.link).join("\n"))}
            >
              {labels.copyAll}
            </Button>
          </div>
          <ul className="space-y-2">
            {links.map((item) => (
              <li
                key={item.link}
                className="border-border flex flex-wrap items-center gap-2 rounded border p-3 text-sm"
              >
                <span className="min-w-0 flex-1 truncate font-mono text-xs">{item.email}</span>
                <Button type="button" variant="outline" onClick={() => copyText(item.link)}>
                  {labels.copy}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="border-border space-y-3 border-t pt-6">
        <h2 className="font-medium">{labels.invitations}</h2>
        {invitations.length ? (
          <ul className="space-y-2">
            {invitations.map((item) => (
              <li
                key={item.invitation_id}
                className="border-border flex flex-wrap items-center gap-2 rounded border p-3 text-sm"
              >
                <span className="min-w-0 flex-1 truncate">
                  {item.display_name} · {item.recipient_email}
                </span>
                <span className="text-muted-foreground">{item.role}</span>
                <span className="text-muted-foreground">{item.state}</span>
                <span className="text-muted-foreground text-xs">
                  {labels.expiresAt} {item.expires_at.slice(0, 10)}
                </span>
                {item.state === "pending" && canInvite ? (
                  <Button
                    type="button"
                    variant="destructive"
                    disabled={busy}
                    onClick={() =>
                      submit(
                        "POST",
                        `/v1/corporate/organizations/${organizationId}/invitations/${item.invitation_id}/revoke`,
                        {
                          schema_version: 1,
                          authorization_revision: authorizationRevision,
                          idempotency_key: crypto.randomUUID(),
                        },
                      )
                    }
                  >
                    {busy ? labels.revoking : labels.revoke}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{labels.noInvitations}</p>
        )}
      </div>

      <div className="border-border space-y-3 border-t pt-6">
        <h2 className="font-medium">{labels.members}</h2>
        {members.length ? (
          <ul className="space-y-2">
            {members.map((item) => (
              <li
                key={item.account_id}
                className="border-border flex flex-wrap items-center gap-2 rounded border p-3 text-sm"
              >
                <span className="min-w-0 flex-1 truncate">
                  {item.display_name ?? item.account_id}
                </span>
                <span className="text-muted-foreground">{item.role}</span>
                <span className="text-muted-foreground">{item.state}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{labels.noMembers}</p>
        )}
      </div>

      {canManagePolicy ? (
        <form
          className="border-border space-y-3 border-t pt-6"
          onSubmit={(event) => {
            event.preventDefault();
            submit("PUT", `/v1/corporate/organizations/${organizationId}/membership/policy`, {
              schema_version: 1,
              allowed_email_domains: restricted
                ? domains
                    .split(/[\s,;]+/)
                    .map((item) => item.trim())
                    .filter(Boolean)
                : [],
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            });
          }}
        >
          <h2 className="font-medium">{labels.domainPolicy}</h2>
          <p className="text-muted-foreground text-sm">{labels.domainPolicyBody}</p>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={restricted}
              onChange={(event) => setRestricted(event.target.checked)}
            />
            {labels.domainRestrict}
          </label>
          {restricted ? (
            <div className="space-y-1">
              <Label htmlFor="corporate-domains">{labels.domains}</Label>
              <Input
                id="corporate-domains"
                value={domains}
                placeholder={labels.domainsPlaceholder}
                onChange={(event) => setDomains(event.target.value)}
              />
              <p className="text-muted-foreground text-xs">{labels.domainsHint}</p>
            </div>
          ) : null}
          <Button type="submit" disabled={busy}>
            {busy ? labels.saving : labels.save}
          </Button>
        </form>
      ) : null}

      {message ? (
        <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
    </section>
  );
}

function SelectField({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
}) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="border-border bg-background h-9 w-full rounded-sm border px-3 text-sm"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
