"use client";

import { toast } from "sonner";

import { Button } from "@/components/atoms/button";
import { Icon } from "@/theme";

export function CopyValue({
  value,
  label,
  copied,
  failed,
}: {
  value: string;
  label: string;
  copied: string;
  failed: string;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <code className="min-w-0 truncate text-sm" title={value}>
        {value}
      </code>
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label={label}
        onClick={() => {
          void navigator.clipboard
            .writeText(value)
            .then(() => toast.success(copied))
            .catch(() => toast.error(failed));
        }}
      >
        <Icon name="copy" size="sm" />
      </Button>
    </div>
  );
}
