"use client";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import {
  EntityEditorField,
  EntityEditorSection,
} from "@/components/molecules/entity-editor-layout";
import type { EntityEditorLink } from "@/lib/entity-editor-contract";

// UI row identity stays out of serialized links and follows an edited object.
const rowKeys = new WeakMap<EntityEditorLink, string>();
let nextRowKey = 0;

function rowKey(link: EntityEditorLink): string {
  let key = rowKeys.get(link);
  if (key === undefined) {
    key = `link-${nextRowKey++}`;
    rowKeys.set(link, key);
  }
  return key;
}

function updatedLink(link: EntityEditorLink, patch: Partial<EntityEditorLink>): EntityEditorLink {
  const updated = { ...link, ...patch };
  rowKeys.set(updated, rowKey(link));
  return updated;
}

export function EntityLinksEditor({
  links,
  max,
  labels,
  onChange,
  disabled = false,
  error,
  fieldErrors = {},
  idPrefix = "entity-link",
}: {
  links: EntityEditorLink[];
  max: number;
  labels: {
    title: string;
    add: string;
    empty: string;
    label: string;
    url: string;
    remove: string;
  };
  onChange: (links: EntityEditorLink[]) => void;
  disabled?: boolean;
  error?: string | null;
  fieldErrors?: Record<string, string>;
  idPrefix?: string;
}) {
  return (
    <EntityEditorSection title={`${labels.title} (up to ${max})`}>
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        {links.length === 0 ? (
          <p className="text-xs text-muted-foreground">{labels.empty}</p>
        ) : (
          <span className="text-xs text-muted-foreground">
            {links.length}/{max}
          </span>
        )}
        <Button
          type="button"
          variant="outline"
          className="min-h-11 sm:min-h-9"
          disabled={disabled || links.length >= max}
          onClick={() => {
            onChange([...links, { label: "", url: "https://" }]);
          }}
        >
          {labels.add}
        </Button>
      </div>
      <div className="space-y-3">
        {links.map((link, index) => {
          const labelId = `${idPrefix}-${index}-label`;
          const urlId = `${idPrefix}-${index}-url`;
          const labelError =
            fieldErrors[`links.${index}.label`] ?? fieldErrors[`links[${index}].label`];
          const urlError = fieldErrors[`links.${index}.url`] ?? fieldErrors[`links[${index}].url`];
          return (
            <div
              key={rowKey(link)}
              className="grid min-w-0 items-end gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto]"
            >
              <EntityEditorField label={labels.label} htmlFor={labelId} required error={labelError}>
                <Input
                  id={labelId}
                  value={link.label}
                  maxLength={60}
                  disabled={disabled}
                  className={
                    labelError ? "border-destructive focus-visible:ring-destructive" : undefined
                  }
                  aria-invalid={Boolean(labelError)}
                  aria-describedby={labelError ? `${labelId}-error` : undefined}
                  onChange={(event) => {
                    onChange(
                      links.map((item, itemIndex) =>
                        itemIndex === index
                          ? updatedLink(item, { label: event.target.value })
                          : item,
                      ),
                    );
                  }}
                />
              </EntityEditorField>
              <EntityEditorField label={labels.url} htmlFor={urlId} required error={urlError}>
                <Input
                  id={urlId}
                  type="url"
                  value={link.url}
                  maxLength={2048}
                  disabled={disabled}
                  className={
                    urlError ? "border-destructive focus-visible:ring-destructive" : undefined
                  }
                  aria-invalid={Boolean(urlError)}
                  aria-describedby={urlError ? `${urlId}-error` : undefined}
                  onChange={(event) => {
                    onChange(
                      links.map((item, itemIndex) =>
                        itemIndex === index ? updatedLink(item, { url: event.target.value }) : item,
                      ),
                    );
                  }}
                />
              </EntityEditorField>
              <Button
                type="button"
                variant="outline"
                className="min-h-11 w-full sm:min-h-9 sm:w-auto"
                disabled={disabled}
                onClick={() => {
                  onChange(links.filter((_, itemIndex) => itemIndex !== index));
                }}
              >
                {labels.remove}
              </Button>
            </div>
          );
        })}
      </div>
      {(error ?? fieldErrors.links) ? (
        <p className="text-xs text-destructive" role="alert">
          {error ?? fieldErrors.links}
        </p>
      ) : null}
    </EntityEditorSection>
  );
}
