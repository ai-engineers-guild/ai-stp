"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/atoms/button";
import { Icon } from "@/theme";

export function ClipboardIconButton({
  value,
  label,
  copiedLabel,
  errorLabel,
}: {
  value: string;
  label: string;
  copiedLabel: string;
  errorLabel?: string;
}) {
  const [status, setStatus] = useState<"idle" | "copied" | "error">("idle");

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setStatus("copied");
      toast.success(copiedLabel);
      window.setTimeout(() => {
        setStatus("idle");
      }, 1400);
    } catch {
      setStatus("error");
      window.setTimeout(() => {
        setStatus("idle");
      }, 1400);
    }
  }

  const announced =
    status === "copied" ? copiedLabel : status === "error" ? (errorLabel ?? label) : label;

  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      aria-label={announced}
      onClick={() => {
        void onCopy();
      }}
    >
      <Icon name={status === "copied" ? "check" : "copy"} size="sm" />
    </Button>
  );
}
