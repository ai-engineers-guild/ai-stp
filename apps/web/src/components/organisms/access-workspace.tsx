"use client";

import { Select } from "@/components/atoms/select";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { EntityActionItems } from "@/components/organisms/entity-action-items";
import { Button } from "@/components/atoms/button";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { CatalogAuthorLink } from "@/components/molecules/catalog-author-link";
import { MutationReference } from "@/components/molecules/mutation-reference";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/atoms/dialog";
import {
  createDirectGrantAction,
  createInvitationAction,
  revokeGrantAction,
} from "@/actions/grants";
import { Link, useRouter } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

export type AccessUser = {
  grantId: string;
  accountId: string;
  displayName: string | null;
  avatarUrl: string | null;
  objectKind?: "component" | "setup";
  stableId?: string;
  major?: number;
};

type Labels = {
  create: string;
  email: string;
  stableId: string;
  kind: string;
  recipientKind: string;
  githubUsername: string;
  userId: string;
  kindComponent: string;
  kindSetup: string;
  peopleWithAccess: string;
  emptyPeople: string;
  revoke: string;
  revokeTitle: string;
  revokeWarning: string;
  cancel: string;
  confirm: string;
  revoking: string;
  copyId: string;
  copied: string;
  report: string;
  more: string;
  user: string;
  referenceId: string;
  githubNote?: string;
};

type AccessWorkspaceProps = {
  users: readonly AccessUser[];
  incomingUsers?: readonly AccessUser[];
  incomingLabel?: string;
  csrfToken: string;
  labels: Labels;
  initialObjectKind?: "component" | "setup" | undefined;
  initialStableId?: string | undefined;
  initialMajor?: number | undefined;
  canCreate?: boolean;
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
  initialObjectKind,
  initialStableId,
  initialMajor,
  onCreate,
}: {
  labels: Labels;
  pending: boolean;
  initialObjectKind?: "component" | "setup" | undefined;
  initialStableId?: string | undefined;
  initialMajor?: number | undefined;
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
  const [stableId, setStableId] = useState(initialStableId ?? "");
  const [kind, setKind] = useState<"component" | "setup">(initialObjectKind ?? "component");
  const major = initialMajor ?? 1;
  const scoped = Boolean(initialObjectKind && initialStableId);

  return (
    <section className="border-border mx-auto max-w-lg space-y-3 rounded-lg border p-4">
      <h2 className="text-lg font-medium tracking-tight">{labels.create}</h2>
      <div className="space-y-2">
        <Label htmlFor="recipient-kind">{labels.recipientKind}</Label>
        <Select
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
        </Select>
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
      {!initialObjectKind ? (
        <div className="space-y-2">
          <Label htmlFor="invite-kind">{labels.kind}</Label>
          <Select
            id="invite-kind"
            className="border-input bg-background h-9 w-full rounded-sm border px-2 text-sm"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value as "component" | "setup");
            }}
          >
            <option value="component">{labels.kindComponent}</option>
            <option value="setup">{labels.kindSetup}</option>
          </Select>
        </div>
      ) : null}
      {!initialStableId ? (
        <Field
          id="invite-stable"
          label={labels.stableId}
          value={stableId}
          onChange={setStableId}
          mono
        />
      ) : null}
      {recipientKind === "github_username" ? (
        <p className="text-muted-foreground text-xs">{labels.githubNote}</p>
      ) : null}
      <Button
        type="button"
        disabled={pending || !recipient || (!scoped && !stableId)}
        onClick={() => {
          onCreate({
            recipientKind,
            recipient,
            kind: initialObjectKind ?? kind,
            stableId: initialStableId ?? stableId,
            major,
          });
          setRecipient("");
        }}
      >
        {labels.create}
      </Button>
    </section>
  );
}

function AccessUserRow({
  user,
  labels,
  pending,
  onRevoke,
}: {
  user: AccessUser;
  labels: Labels;
  pending: boolean;
  onRevoke: (grantId: string) => void;
}) {
  const [reportOpen, setReportOpen] = useState(false);

  async function copyId() {
    await navigator.clipboard.writeText(user.grantId);
    toast.success(labels.copied);
  }

  return (
    <li className="border-border flex items-center gap-3 border-b px-3 py-2 last:border-b-0">
      <div className="min-w-0 flex-1">
        <CatalogAuthorLink
          accountId={user.accountId}
          displayName={user.displayName}
          avatarUrl={user.avatarUrl}
          verified={false}
          verifiedLabel={labels.user}
        />
        {user.objectKind && user.stableId ? (
          <Link
            href={`/catalog/${user.objectKind === "component" ? "components" : "setups"}/${user.stableId}`}
            className="text-muted-foreground block truncate font-mono text-xs hover:underline"
          >
            {user.stableId}
            {user.major ? `@${user.major}.x` : ""}
          </Link>
        ) : null}
      </div>
      <Menu modal={false}>
        <MenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon" aria-label={labels.more}>
            <Icon name="more" size="sm" />
          </Button>
        </MenuTrigger>
        <MenuContent>
          <EntityActionItems
            subject={{ kind: "grant", id: user.grantId }}
            entries={{
              report: (
                <MenuItem
                  onSelect={() => {
                    setReportOpen(true);
                  }}
                >
                  <Icon name="flag" size="sm" />
                  {labels.report}
                </MenuItem>
              ),
              copy_id: (
                <MenuItem
                  onSelect={() => {
                    void copyId();
                  }}
                >
                  <Icon name="copy" size="sm" />
                  {labels.copyId}
                </MenuItem>
              ),
              revoke: (
                <MenuItem
                  disabled={pending}
                  onSelect={() => {
                    onRevoke(user.grantId);
                  }}
                >
                  <Icon name="close" size="sm" />
                  {labels.revoke}
                </MenuItem>
              ),
            }}
          />
        </MenuContent>
      </Menu>
      <ContactReportDialog
        kind="author"
        target={user.accountId}
        label={labels.report}
        hideTrigger
        open={reportOpen}
        onOpenChange={setReportOpen}
      />
    </li>
  );
}

export function AccessWorkspace({
  users,
  incomingUsers = [],
  incomingLabel,
  csrfToken,
  labels,
  initialObjectKind,
  initialStableId,
  initialMajor,
  canCreate = true,
}: AccessWorkspaceProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [operationId, setOperationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);

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

  function confirmRevoke() {
    if (!revokeTarget) return;
    const grantId = revokeTarget;
    setRevokeTarget(null);
    run(() => revokeGrantAction({ csrfToken, grantId, reason: "" }));
  }

  return (
    <div className="space-y-8">
      {canCreate ? (
        <InviteForm
          labels={labels}
          pending={pending}
          initialObjectKind={initialObjectKind}
          initialStableId={initialStableId}
          initialMajor={initialMajor}
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
      ) : null}

      <section className="space-y-3">
        <h2 className="text-lg font-medium tracking-tight">{labels.peopleWithAccess}</h2>
        {users.length === 0 ? (
          <p className="text-muted-foreground text-sm">{labels.emptyPeople}</p>
        ) : (
          <ul className="border-border rounded-lg border">
            {users.map((user) => (
              <AccessUserRow
                key={user.grantId}
                user={user}
                labels={labels}
                pending={pending}
                onRevoke={setRevokeTarget}
              />
            ))}
          </ul>
        )}
      </section>

      {incomingUsers.length ? (
        <section className="space-y-3">
          <h2 className="text-lg font-medium tracking-tight">{incomingLabel}</h2>
          <ul className="border-border rounded-lg border">
            {incomingUsers.map((user) => (
              <AccessUserRow
                key={user.grantId}
                user={user}
                labels={labels}
                pending={pending}
                onRevoke={setRevokeTarget}
              />
            ))}
          </ul>
        </section>
      ) : null}

      <div className="mx-auto max-w-lg space-y-2">
        <MutationReference label={labels.referenceId} operationId={operationId} />
        {error ? (
          <p className="text-destructive text-sm" role="alert">
            {error}
          </p>
        ) : null}
      </div>

      <Dialog
        open={revokeTarget !== null}
        onOpenChange={(open) => {
          if (!open && !pending) setRevokeTarget(null);
        }}
      >
        <DialogContent closeLabel={labels.cancel}>
          <DialogHeader>
            <DialogTitle>{labels.revokeTitle}</DialogTitle>
            <DialogDescription>{labels.revokeWarning}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              disabled={pending}
              onClick={() => {
                setRevokeTarget(null);
              }}
            >
              {labels.cancel}
            </Button>
            <Button type="button" variant="destructive" disabled={pending} onClick={confirmRevoke}>
              {pending ? labels.revoking : labels.confirm}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
