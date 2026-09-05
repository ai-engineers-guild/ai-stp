"use client";

import { useState, useTransition } from "react";
import { useRouter } from "@/lib/i18n/navigation";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { MutationReference } from "@/components/molecules/mutation-reference";
import { staffLifecycleAction, staffTriageAction } from "@/actions/staff";

type StaffCaseActionsProps = {
  csrfToken: string;
  caseId: string;
  objectKind: "component" | "setup" | "";
  stableId: string;
  version: string;
  labels: {
    triage: string;
    reason: string;
    confirm: string;
    block: string;
    hide: string;
    restore: string;
    operatorNote: string;
    lifecycle: string;
    referenceId: string;
    stateTriaged: string;
    stateAwaitingAuthor: string;
    stateResolved: string;
    stateDismissed: string;
  };
};

type TriageState = "triaged" | "awaiting_author" | "resolved" | "dismissed";
type LifecycleAction = "block" | "hide" | "restore";

function LifecycleControls({
  labels,
  pending,
  onAction,
}: {
  labels: StaffCaseActionsProps["labels"];
  pending: boolean;
  onAction: (action: LifecycleAction) => void;
}) {
  return (
    <section className="border-border space-y-3 rounded-lg border p-4">
      <h2 className="text-lg font-medium tracking-tight">{labels.lifecycle}</h2>
      <div className="flex flex-wrap gap-2">
        {(["block", "hide", "restore"] as const).map((action) => (
          <Button
            key={action}
            type="button"
            variant={action === "restore" ? "outline" : "destructive"}
            size="sm"
            disabled={pending}
            onClick={() => {
              onAction(action);
            }}
          >
            {labels[action]}
          </Button>
        ))}
      </div>
    </section>
  );
}

export function StaffCaseActions({
  csrfToken,
  caseId,
  objectKind,
  stableId,
  version,
  labels,
}: StaffCaseActionsProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [reason, setReason] = useState("");
  const [state, setState] = useState<TriageState>("triaged");
  const [operationId, setOperationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function run(action: () => Promise<{ operationId: string | null }>) {
    if (!reason.trim()) {
      setError("reason");
      return;
    }
    if (!window.confirm(labels.confirm)) {
      return;
    }
    setError(null);
    startTransition(async () => {
      try {
        const result = await action();
        setOperationId(result.operationId);
        router.refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "error");
      }
    });
  }

  const lifecycle = (action: LifecycleAction) => {
    if (objectKind !== "component" && objectKind !== "setup") {
      return;
    }
    run(() =>
      staffLifecycleAction({
        csrfToken,
        objectKind,
        stableId,
        version,
        action,
        reason,
      }),
    );
  };

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div className="space-y-2">
        <Label htmlFor="staff-reason">{labels.reason}</Label>
        <Input
          id="staff-reason"
          value={reason}
          onChange={(event) => {
            setReason(event.target.value);
          }}
          maxLength={500}
        />
      </div>

      <section className="border-border space-y-3 rounded-lg border p-4">
        <h2 className="text-lg font-medium tracking-tight">{labels.triage}</h2>
        <select
          className="border-input bg-background h-9 w-full rounded-sm border px-2 font-mono text-xs"
          value={state}
          onChange={(event) => {
            setState(event.target.value as TriageState);
          }}
        >
          <option value="triaged">{labels.stateTriaged}</option>
          <option value="awaiting_author">{labels.stateAwaitingAuthor}</option>
          <option value="resolved">{labels.stateResolved}</option>
          <option value="dismissed">{labels.stateDismissed}</option>
        </select>
        <Button
          type="button"
          disabled={pending}
          onClick={() => {
            run(() => staffTriageAction({ csrfToken, caseId, state, reason }));
          }}
        >
          {labels.triage}
        </Button>
      </section>

      {objectKind === "component" || objectKind === "setup" ? (
        <LifecycleControls labels={labels} pending={pending} onAction={lifecycle} />
      ) : null}

      <p className="text-muted-foreground text-sm">{labels.operatorNote}</p>

      <MutationReference label={labels.referenceId} operationId={operationId} />
      {error ? (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
