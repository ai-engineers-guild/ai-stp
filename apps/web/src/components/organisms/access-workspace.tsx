"use client";

import { useState, useTransition } from "react";
import { useRouter } from "@/lib/i18n/navigation";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { MutationReference } from "@/components/molecules/mutation-reference";
import {
  createDirectGrantAction,
  createInvitationAction,
  revokeGrantAction,
  revokeInvitationAction,
} from "@/actions/grants";
import type { AccessGrantResponse, GrantInvitationResponse } from "@/lib/api/generated/types.gen";

type Labels = {
  invitations: string;
  grants: string;
  emptyInvitations: string;
  emptyGrants: string;
  create: string;
  email: string;
  major: string;
  stableId: string;
  kind: string;
  recipientKind: string;
  githubUsername: string;
  userId: string;
  kindComponent: string;
  kindSetup: string;
  revoke: string;
  revokeWarning: string;
  reason: string;
  confirm: string;
  cancel: string;
  referenceId: string;
};

type AccessWorkspaceProps = {
  invitations: readonly GrantInvitationResponse[];
  grants: readonly AccessGrantResponse[];
  csrfToken: string;
  labels: Labels;
};

function Field({
  id,
  label,
  value,
  onChange,
  mono,
  type = "text",
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  mono?: boolean;
  type?: string;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        className={mono ? "font-mono text-xs" : undefined}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        autoComplete={type === "email" ? "email" : undefined}
      />
    </div>
  );
}

function InviteForm({
  labels,
  pending,
  onCreate,
}: {
  labels: Labels;
  pending: boolean;
  onCreate: (input: {
    recipientKind: "verified_email" | "github_username" | "user_id";
    recipient: string;
    kind: "component" | "setup";
    stableId: string;
    major: number;
  }) => void;
}) {
  const [recipient, setRecipient] = useState("");
  const [recipientKind, setRecipientKind] = useState<
    "verified_email" | "github_username" | "user_id"
  >("verified_email");
  const [stableId, setStableId] = useState("");
  const [major, setMajor] = useState("1");
  const [kind, setKind] = useState<"component" | "setup">("component");
  return (
    <section className="border-border mx-auto max-w-lg space-y-3 rounded-lg border p-4">
      <h2 className="text-lg font-medium tracking-tight">{labels.create}</h2>
      <div className="space-y-2">
        <Label htmlFor="recipient-kind">{labels.recipientKind}</Label>
        <select
          id="recipient-kind"
          className="border-input bg-background h-9 w-full rounded-sm border px-2 text-sm"
          value={recipientKind}
          onChange={(event) => {
            setRecipientKind(
              event.target.value as "verified_email" | "github_username" | "user_id",
            );
            setRecipient("");
          }}
        >
          <option value="verified_email">{labels.email}</option>
          <option value="github_username">{labels.githubUsername}</option>
          <option value="user_id">{labels.userId}</option>
        </select>
      </div>
      <Field
        id="invite-recipient"
        label={
          recipientKind === "verified_email"
            ? labels.email
            : recipientKind === "github_username"
              ? labels.githubUsername
              : labels.userId
        }
        value={recipient}
        onChange={setRecipient}
        type={recipientKind === "verified_email" ? "email" : "text"}
      />
      <div className="space-y-2">
        <Label htmlFor="invite-kind">{labels.kind}</Label>
        <select
          id="invite-kind"
          className="border-input bg-background h-9 w-full rounded-sm border px-2 text-sm"
          value={kind}
          onChange={(event) => {
            setKind(event.target.value as "component" | "setup");
          }}
        >
          <option value="component">{labels.kindComponent}</option>
          <option value="setup">{labels.kindSetup}</option>
        </select>
      </div>
      <Field
        id="invite-stable"
        label={labels.stableId}
        value={stableId}
        onChange={setStableId}
        mono
      />
      <Field id="invite-major" label={labels.major} value={major} onChange={setMajor} mono />
      <Button
        type="button"
        disabled={pending || !recipient || !stableId}
        onClick={() => {
          onCreate({
            recipientKind,
            recipient,
            kind,
            stableId,
            major: Number.parseInt(major, 10) || 1,
          });
          setRecipient("");
        }}
      >
        {labels.create}
      </Button>
    </section>
  );
}

export function AccessWorkspace({ invitations, grants, csrfToken, labels }: AccessWorkspaceProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [operationId, setOperationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  function run(task: () => Promise<{ operationId: string | null }>) {
    setError(null);
    startTransition(async () => {
      try {
        const result = await task();
        setOperationId(result.operationId);
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "error");
      }
    });
  }

  function confirmRevoke(task: () => Promise<{ operationId: string | null }>) {
    if (!window.confirm(labels.revokeWarning)) {
      return;
    }
    run(task);
  }

  return (
    <div className="space-y-8">
      <InviteForm
        labels={labels}
        pending={pending}
        onCreate={(input) => {
          run(() =>
            input.recipientKind === "verified_email"
              ? createInvitationAction({
                  csrfToken,
                  objectKind: input.kind,
                  stableId: input.stableId,
                  major: input.major,
                  recipientEmail: input.recipient,
                })
              : createDirectGrantAction({
                  csrfToken,
                  objectKind: input.kind,
                  stableId: input.stableId,
                  major: input.major,
                  recipientKind: input.recipientKind,
                  recipient: input.recipient,
                }),
          );
        }}
      />

      <section className="space-y-3">
        <h2 className="text-lg font-medium tracking-tight">{labels.invitations}</h2>
        {invitations.length === 0 ? (
          <p className="text-muted-foreground text-sm">{labels.emptyInvitations}</p>
        ) : (
          <ul className="divide-border border-border divide-y rounded-lg border">
            {invitations.map((item) => (
              <li
                key={item.invitation_id}
                className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-1">
                  <p className="font-mono text-xs">{item.stable_id}</p>
                  <p className="text-muted-foreground font-mono text-xs">
                    {labels.major} {item.major} · {item.object_kind}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="font-mono text-xs">
                    {item.state}
                  </Badge>
                  {item.state === "pending" ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={pending}
                      onClick={() => {
                        confirmRevoke(() =>
                          revokeInvitationAction({
                            csrfToken,
                            invitationId: item.invitation_id,
                            reason,
                          }),
                        );
                      }}
                    >
                      {labels.revoke}
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-medium tracking-tight">{labels.grants}</h2>
        {grants.length === 0 ? (
          <p className="text-muted-foreground text-sm">{labels.emptyGrants}</p>
        ) : (
          <ul className="divide-border border-border divide-y rounded-lg border">
            {grants.map((item) => (
              <li
                key={item.grant_id}
                className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="space-y-1">
                  <p className="font-mono text-xs">{item.stable_id}</p>
                  <p className="text-muted-foreground font-mono text-xs">
                    {labels.major} {item.major} · {item.state}
                  </p>
                  {"recipient_kind" in item && typeof item.recipient === "string" ? (
                    <p className="text-muted-foreground font-mono text-xs">
                      {String(item.recipient_kind)}: {item.recipient}
                    </p>
                  ) : null}
                </div>
                {item.state === "active" ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="destructive"
                    disabled={pending}
                    onClick={() => {
                      confirmRevoke(() =>
                        revokeGrantAction({
                          csrfToken,
                          grantId: item.grant_id,
                          reason,
                        }),
                      );
                    }}
                  >
                    {labels.revoke}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="mx-auto max-w-lg space-y-2">
        <Field id="revoke-reason" label={labels.reason} value={reason} onChange={setReason} />
        <MutationReference label={labels.referenceId} operationId={operationId} />
        {error ? (
          <p className="text-destructive text-sm" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
