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
  hydrationReady,
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
  hydrationReady?: boolean | undefined;
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
      data-hydrated={hydrationReady === undefined ? undefined : String(hydrationReady)}
      className={`w-full min-w-0 rounded-lg border border-border bg-card p-5 shadow-sm sm:p-6 ${className}`}
    >
      <header className="space-y-1 border-b border-border pb-5">
        <h2 className="text-xl font-medium tracking-tight">{title}</h2>
        {description ? (
          <p className="max-w-[70ch] text-sm leading-relaxed text-muted-foreground">
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
        {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
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
          <span className="ml-1 text-destructive before:content-['*']" aria-hidden="true" />
        ) : null}
      </label>
      {children}
      {hint ? <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p> : null}
      {error ? (
        <p
          id={htmlFor ? `${htmlFor}-error` : undefined}
          className="text-xs text-destructive"
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
    <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3" role="alert">
      <p className="text-sm font-medium text-destructive">{error ?? summary}</p>
      {entries.length ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-destructive">
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
