"use client";

import { useState } from "react";

import { Label } from "@/components/atoms/label";
import { Switch } from "@/components/atoms/switch";
import { Icon, type IconName } from "@/theme";
import { FieldHint } from "@/components/molecules/field-hint";

type SwitchStatus = {
  on: string;
  off: string;
  onHint?: string;
  offHint?: string;
};

/**
 * Label + Switch row for policy forms. `status` renders the live on/off word
 * and caption beside the control; `icon` frames the row as a card header.
 * The hidden input inside Switch keeps the plain "true"/"false" form contract.
 */
export function SwitchRow({
  id,
  name,
  label,
  hint,
  description,
  icon,
  status,
  value,
  disabled,
  onCheckedChange,
}: {
  id: string;
  name: string;
  label: string;
  hint?: string | undefined;
  description?: string | undefined;
  icon?: IconName | undefined;
  status?: SwitchStatus | undefined;
  value: boolean;
  disabled: boolean;
  onCheckedChange?: ((checked: boolean) => void) | undefined;
}) {
  const [on, setOn] = useState(value);
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="flex min-w-0 items-center gap-3">
        {icon ? (
          <span
            aria-hidden
            className="border-border bg-muted/40 text-muted-foreground grid size-10 shrink-0 place-items-center rounded-md border"
          >
            <Icon name={icon} size="sm" />
          </span>
        ) : null}
        <span className="min-w-0">
          <span className="flex items-center gap-1">
            <Label htmlFor={id} className="font-medium">
              {label}
            </Label>
            {hint ? <FieldHint text={hint} /> : null}
          </span>
          {description ? (
            <span className="text-muted-foreground mt-0.5 block text-sm">{description}</span>
          ) : null}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-3">
        <Switch
          id={id}
          name={name}
          defaultChecked={value}
          disabled={disabled}
          aria-label={label}
          onCheckedChange={(checked) => {
            setOn(checked);
            onCheckedChange?.(checked);
          }}
        />
        {status ? (
          <span className="hidden w-44 sm:block">
            <span className="block text-sm font-medium">{on ? status.on : status.off}</span>
            <span className="text-muted-foreground block text-xs">
              {on ? (status.onHint ?? "") : (status.offHint ?? "")}
            </span>
          </span>
        ) : null}
      </span>
    </div>
  );
}
