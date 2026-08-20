"use client";

import { useRouter } from "@/lib/i18n/navigation";
import { useState, useTransition } from "react";

import { Button } from "@/components/atoms/button";
import { startPublicationAction } from "@/actions/publications";

type StartPublicationFormProps = {
  objectKind: "component" | "setup";
  stableId: string;
  version: string;
  deviceId: string;
  csrfToken: string;
  labels: {
    start: string;
    starting: string;
  };
};

export function StartPublicationForm({
  objectKind,
  stableId,
  version,
  deviceId,
  csrfToken,
  labels,
}: StartPublicationFormProps) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <div className="space-y-2">
      <Button
        type="button"
        disabled={pending}
        onClick={() => {
          setError(null);
          startTransition(async () => {
            try {
              const result = await startPublicationAction({
                objectKind,
                stableId,
                version,
                deviceId,
                csrfToken,
              });
              router.push(`/publications/${result.planId}`);
            } catch (err) {
              setError(err instanceof Error ? err.message : "error");
            }
          });
        }}
      >
        {pending ? labels.starting : labels.start}
      </Button>
      {error ? (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
