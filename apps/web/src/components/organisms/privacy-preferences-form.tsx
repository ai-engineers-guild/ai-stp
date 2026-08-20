"use client";

import { useState, useTransition } from "react";

import { updatePrivacyAction } from "@/actions/account";
import { Button } from "@/components/atoms/button";

type PrivacyPreferencesFormProps = {
  csrfToken: string;
  initialShowProfilePublicly: boolean;
  initialAllowPublisherListing: boolean;
  labels: {
    showProfilePublicly: string;
    allowPublisherListing: string;
    save: string;
    saving: string;
    saved: string;
    failed: string;
  };
};

export function PrivacyPreferencesForm({
  csrfToken,
  initialShowProfilePublicly,
  initialAllowPublisherListing,
  labels,
}: PrivacyPreferencesFormProps) {
  const [showProfilePublicly, setShowProfilePublicly] = useState(initialShowProfilePublicly);
  const [allowPublisherListing, setAllowPublisherListing] = useState(initialAllowPublisherListing);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function save() {
    setMessage(null);
    startTransition(async () => {
      const result = await updatePrivacyAction({
        csrfToken,
        showProfilePublicly,
        allowPublisherListing,
      });
      setMessage(result.ok ? labels.saved : labels.failed);
    });
  }

  return (
    <div className="border-border bg-card min-w-0 space-y-5 rounded-lg border p-5 shadow-sm sm:p-6">
      <label className="flex min-h-11 cursor-pointer items-center justify-between gap-4">
        <span className="min-w-0 text-sm">{labels.showProfilePublicly}</span>
        <input
          type="checkbox"
          checked={showProfilePublicly}
          onChange={(event) => {
            setShowProfilePublicly(event.target.checked);
          }}
          className="accent-primary h-5 w-5 shrink-0"
        />
      </label>
      <label className="flex min-h-11 cursor-pointer items-center justify-between gap-4">
        <span className="min-w-0 text-sm">{labels.allowPublisherListing}</span>
        <input
          type="checkbox"
          checked={allowPublisherListing}
          onChange={(event) => {
            setAllowPublisherListing(event.target.checked);
          }}
          className="accent-primary h-5 w-5 shrink-0"
        />
      </label>
      <div className="flex flex-col gap-3 pt-1 sm:flex-row sm:flex-wrap sm:items-center">
        <Button
          type="button"
          className="min-h-11 w-full sm:w-auto"
          onClick={save}
          disabled={isPending}
        >
          {isPending ? labels.saving : labels.save}
        </Button>
        {message ? (
          <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
            {message}
          </p>
        ) : null}
      </div>
    </div>
  );
}
