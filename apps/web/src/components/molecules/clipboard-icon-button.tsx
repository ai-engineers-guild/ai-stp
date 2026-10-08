"use client";

import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button, type ButtonProps } from "@/components/atoms/button";
import { Icon } from "@/theme";

/**
 * Shared clipboard copy action. Icon-only by default; pass `children` for a
 * labeled button — the accessible name still switches to `copiedLabel`.
 */
export function ClipboardIconButton({
  value,
  label,
  copiedLabel,
  errorLabel,
  variant = "outline",
  className,
  children,
}: {
  value: string;
  label: string;
  copiedLabel: string;
  errorLabel?: string;
  variant?: ButtonProps["variant"];
  className?: string;
  children?: ReactNode;
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

  if (children !== undefined) {
    return (
      <Button
        type="button"
        variant={variant}
        className={className}
        aria-label={announced}
        onClick={() => {
          void onCopy();
        }}
      >
        <Icon name={status === "copied" ? "check" : "copy"} size="sm" />
        {status === "copied" ? copiedLabel : children}
      </Button>
    );
  }

  return (
    <Button
      type="button"
      variant={variant}
      size="icon"
      className={className}
      aria-label={announced}
      onClick={() => {
        void onCopy();
      }}
    >
      <Icon name={status === "copied" ? "check" : "copy"} size="sm" />
    </Button>
  );
}
