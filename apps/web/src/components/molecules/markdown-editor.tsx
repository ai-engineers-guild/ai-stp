"use client";

import { useMemo } from "react";

import { Button } from "@/components/atoms/button";
import { Textarea } from "@/components/atoms/textarea";
import { EntityEditorField } from "@/components/molecules/entity-editor-layout";
import { renderMarkdownOnServer } from "@/lib/markdown/render";

export function MarkdownEditor({
  id,
  label,
  value,
  mode,
  onChange,
  onModeChange,
  maxLength,
  hint,
  error,
  disabled = false,
  labels,
}: {
  id: string;
  label: string;
  value: string;
  mode: "write" | "preview";
  onChange: (value: string) => void;
  onModeChange: (mode: "write" | "preview") => void;
  maxLength: number;
  hint?: string | undefined;
  error?: string | null | undefined;
  disabled?: boolean | undefined;
  labels: { write: string; preview: string };
}) {
  const rendered = useMemo(() => renderMarkdownOnServer(value), [value]);
  return (
    <EntityEditorField label={label} htmlFor={id} hint={hint} error={error}>
      <fieldset className="flex min-w-0 flex-wrap justify-end gap-1">
        <Button
          type="button"
          size="sm"
          variant={mode === "write" ? "secondary" : "ghost"}
          aria-pressed={mode === "write"}
          onClick={() => {
            onModeChange("write");
          }}
          disabled={disabled}
        >
          {labels.write}
        </Button>
        <Button
          type="button"
          size="sm"
          variant={mode === "preview" ? "secondary" : "ghost"}
          aria-pressed={mode === "preview"}
          onClick={() => {
            onModeChange("preview");
          }}
          disabled={disabled}
        >
          {labels.preview}
        </Button>
      </fieldset>
      {mode === "preview" ? (
        <section
          className="prose-sm min-h-36 w-full overflow-x-auto rounded-sm border border-input bg-background px-3 py-2 text-sm leading-relaxed [&_a]:underline [&_code]:font-mono [&_ol]:list-decimal [&_ol]:pl-5 [&_table]:w-full [&_ul]:list-disc [&_ul]:pl-5"
          aria-label={label}
          // biome-ignore lint/security/noDangerouslySetInnerHtml: Only output from the shared escaping Markdown renderer reaches this HTML boundary.
          dangerouslySetInnerHTML={{ __html: rendered.html || "<p></p>" }}
        />
      ) : (
        <Textarea
          id={id}
          className={`min-h-36 font-mono ${error ? "border-destructive focus-visible:ring-destructive" : ""}`}
          value={value}
          maxLength={maxLength}
          disabled={disabled}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${id}-error` : undefined}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      )}
      <p className="font-mono text-xs text-muted-foreground">
        {value.length}/{maxLength}
      </p>
    </EntityEditorField>
  );
}
