import { Fragment, type ReactNode } from "react";

import type { EntityEditorBlock, EntityEditorConfig } from "@/lib/entity-editor-contract";

export function EntityEditorLayout({
  config,
  title,
  description,
  children,
  blocks,
  beforeBlocks,
  afterBlocks,
  footer,
  className = "",
}: {
  config: EntityEditorConfig;
  title: string;
  description?: string | undefined;
  children?: ReactNode;
  blocks?: Partial<Record<EntityEditorBlock, ReactNode>>;
  beforeBlocks?: ReactNode;
  afterBlocks?: ReactNode;
  footer?: ReactNode | undefined;
  className?: string | undefined;
}) {
  const content = blocks ? (
    <>
      {beforeBlocks}
      {config.blocks.map((block) => {
        const content = blocks[block];
        return content ? <Fragment key={block}>{content}</Fragment> : null;
      })}
      {afterBlocks}
    </>
  ) : (
    children
  );

  return (
    <div
      data-ui="entity-editor-layout"
      data-entity-kind={config.kind}
      className={`border-border bg-card w-full min-w-0 rounded-lg border p-5 shadow-sm sm:p-6 ${className}`}
    >
      <header className="border-border space-y-1 border-b pb-5">
        <h2 className="text-xl font-medium tracking-tight">{title}</h2>
        {description ? (
          <p className="text-muted-foreground max-w-[70ch] text-sm leading-relaxed">
            {description}
          </p>
        ) : null}
      </header>
      <div className="min-w-0 space-y-6 pt-5">{content}</div>
      {footer ? <div className="pt-5">{footer}</div> : null}
    </div>
  );
}

export function EntityEditorSection({
  title,
  description,
  children,
  className = "",
}: {
  title: string;
  description?: string | undefined;
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <section data-ui="entity-editor-section" className={`min-w-0 space-y-3 ${className}`}>
      <header className="space-y-1">
        <h3 className="text-sm font-medium">{title}</h3>
        {description ? <p className="text-muted-foreground text-xs">{description}</p> : null}
      </header>
      {children}
    </section>
  );
}

export function EntityEditorField({
  label,
  htmlFor,
  required = false,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor?: string | undefined;
  required?: boolean;
  hint?: string | undefined;
  error?: string | null | undefined;
  children: ReactNode;
}) {
  return (
    <div data-ui="entity-editor-field" className="min-w-0 space-y-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
        {required ? (
          <span className="text-destructive ml-1 before:content-['*']" aria-hidden="true" />
        ) : null}
      </label>
      {children}
      {hint ? <p className="text-muted-foreground text-xs leading-relaxed">{hint}</p> : null}
      {error ? (
        <p
          id={htmlFor ? `${htmlFor}-error` : undefined}
          className="text-destructive text-xs"
          role="alert"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function EntityEditorErrorSummary({
  error,
  fieldErrors,
  summary,
  fieldLabel,
}: {
  error?: string | null;
  fieldErrors: Record<string, string>;
  summary: string;
  fieldLabel: (path: string) => string;
}) {
  const entries = Object.entries(fieldErrors);
  if (!error && !entries.length) return null;
  return (
    <div className="border-destructive/50 bg-destructive/10 rounded-md border p-3" role="alert">
      <p className="text-destructive text-sm font-medium">{error ?? summary}</p>
      {entries.length ? (
        <ul className="text-destructive mt-2 list-disc space-y-1 pl-5 text-xs">
          {entries.map(([path, message]) => (
            <li key={path}>
              <span className="font-medium">{fieldLabel(path)}</span>: {message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
