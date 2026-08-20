"use client";

import { useId, useState } from "react";

import { CliCopyBlock } from "@/components/molecules/cli-copy-block";
import type { ContextBudgetLabels } from "@/components/organisms/context-budget-labels";

export function ContextBudgetLocalCheck({
  command,
  labels,
}: {
  command: string;
  labels: ContextBudgetLabels;
}) {
  const [open, setOpen] = useState(false);
  const buttonId = useId();
  const panelId = useId();
  return (
    <div>
      <button
        type="button"
        id={buttonId}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          setOpen((value) => !value);
        }}
        className="focus-visible:ring-ring text-sm font-medium focus-visible:ring-2 focus-visible:outline-none"
      >
        {labels.checkLocally}
      </button>
      {open ? (
        <div id={panelId} role="region" aria-labelledby={buttonId} className="mt-3">
          <CliCopyBlock
            command={command}
            title={labels.localCommandTitle}
            description={labels.localCommandBody}
            copyLabel={labels.copy}
            copiedLabel={labels.copied}
            errorLabel={labels.copyError}
            docsLabel={labels.docs}
            variant="plain"
          />
        </div>
      ) : null}
    </div>
  );
}
