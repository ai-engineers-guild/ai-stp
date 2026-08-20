"use client";

import { useState, useTransition } from "react";
import { useRouter } from "@/lib/i18n/navigation";

import { Button } from "@/components/atoms/button";
import { MutationReference } from "@/components/molecules/mutation-reference";
import { confirmPublicationAction } from "@/actions/publications";

type ConfirmPublicationFormProps = {
  planId: string;
  planHash: string;
  csrfToken: string;
  labels: {
    confirm: string;
    confirming: string;
    warning: string;
  };
};

export function ConfirmPublicationForm({
  planId,
  planHash,
  csrfToken,
  labels,
}: ConfirmPublicationFormProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [operationId, setOperationId] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">{labels.warning}</p>
      <Button
        type="button"
        disabled={pending}
        onClick={() => {
          setError(null);
          startTransition(async () => {
            try {
              const result = await confirmPublicationAction({
                planId,
                planHash,
                csrfToken,
              });
              setOperationId(result.operationId);
              router.refresh();
            } catch (err) {
              setError(err instanceof Error ? err.message : "error");
            }
          });
        }}
      >
        {pending ? labels.confirming : labels.confirm}
      </Button>
      <MutationReference label="Reference id" operationId={operationId} />
      {error ? (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
