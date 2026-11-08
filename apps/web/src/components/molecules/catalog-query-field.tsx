"use client";

import { useId, useMemo, useState } from "react";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import {
  CATALOG_QL_FIELDS,
  CATALOG_QL_OPERATORS,
  catalogQlWordKind,
  completeCatalogQlToken,
  correctCatalogQuery,
  highlightCatalogQuery,
  suggestCatalogQlWords,
} from "@/lib/catalog-query-assist";
import { Icon } from "@/theme";

export function CatalogQueryField({
  label,
  placeholder,
  submitLabel,
  defaultValue,
  correctionLabel,
  fieldsLabel,
  operatorsLabel,
  literalHint,
}: {
  label: string;
  placeholder: string;
  submitLabel: string;
  defaultValue: string;
  correctionLabel: string;
  fieldsLabel: string;
  operatorsLabel: string;
  literalHint: string;
}) {
  const listId = useId();
  const [value, setValue] = useState(defaultValue);
  const [activeIndex, setActiveIndex] = useState(-1);
  const correction = useMemo(() => correctCatalogQuery(value), [value]);
  const suggestions = useMemo(() => suggestCatalogQlWords(value), [value]);
  const highlighted = useMemo(() => highlightCatalogQuery(value), [value]);

  function apply(word: string) {
    setValue((current) => completeCatalogQlToken(current, word));
    setActiveIndex(-1);
  }

  return (
    <div className="min-w-0 space-y-3">
      <Label htmlFor="catalog-search">{label}</Label>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Icon
            name="search"
            size="sm"
            className="pointer-events-none absolute top-3 left-3 text-muted-foreground"
          />
          <Input
            id="catalog-search"
            name="q"
            type="search"
            role="combobox"
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
              setActiveIndex(-1);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown" && suggestions.length) {
                event.preventDefault();
                setActiveIndex((index) => (index + 1) % suggestions.length);
              } else if (event.key === "ArrowUp" && suggestions.length) {
                event.preventDefault();
                setActiveIndex((index) => (index <= 0 ? suggestions.length - 1 : index - 1));
              } else if (event.key === "Enter" && activeIndex >= 0) {
                const word = suggestions[activeIndex];
                if (word) {
                  event.preventDefault();
                  apply(word);
                }
              } else if (event.key === "Escape") {
                setActiveIndex(-1);
              }
            }}
            placeholder={placeholder}
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            className="h-11 pl-10 font-mono"
            aria-autocomplete="list"
            aria-expanded={suggestions.length > 0}
            aria-controls={listId}
            aria-activedescendant={
              activeIndex >= 0 ? `${listId}-${suggestions[activeIndex] ?? ""}` : undefined
            }
            aria-describedby="catalog-query-assist"
          />
          {suggestions.length ? (
            <div
              id={listId}
              role="listbox"
              className="absolute z-10 mt-1 w-full rounded-sm border border-border bg-popover py-1 shadow-sm"
            >
              {suggestions.map((word, index) => (
                <div key={word} role="presentation">
                  <button
                    id={`${listId}-${word}`}
                    type="button"
                    role="option"
                    aria-selected={index === activeIndex}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      apply(word);
                    }}
                    className={`block w-full px-3 py-1.5 text-left font-mono text-sm ${
                      index === activeIndex ? "bg-muted" : "hover:bg-muted"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <span className="font-medium">{word}</span>
                      {/* Unrendered between flex items, but it keeps the option's
                          accessible name two words where no layout blockifies them. */}{" "}
                      <span className="font-sans text-xs text-muted-foreground">
                        {catalogQlWordKind(word) === "field" ? fieldsLabel : operatorsLabel}
                      </span>
                    </span>
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <Button type="submit" className="min-h-11 w-full sm:w-auto">
          {submitLabel}
        </Button>
      </div>
      {value ? <CatalogQueryPreview segments={highlighted} /> : null}
      <CatalogQlReference
        fieldsLabel={fieldsLabel}
        operatorsLabel={operatorsLabel}
        literalHint={literalHint}
      />
      <div id="catalog-query-assist" className="min-h-6" aria-live="polite">
        {correction !== value ? (
          <button
            type="button"
            onClick={() => {
              setValue(correction);
            }}
            className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
          >
            {correctionLabel}: <span className="font-mono">{correction}</span>
          </button>
        ) : null}
      </div>
    </div>
  );
}

function CatalogQueryPreview({ segments }: { segments: ReturnType<typeof highlightCatalogQuery> }) {
  return (
    <div
      aria-hidden="true"
      className="min-w-0 overflow-x-auto rounded-sm border border-border bg-muted/40 px-3 py-2 font-mono text-sm whitespace-pre"
    >
      {segments.map((segment, index) => (
        <span
          // biome-ignore lint/suspicious/noArrayIndexKey: A stateless token's source position distinguishes repeated syntax.
          key={`${index}-${segment.text}`}
          className={
            segment.kind === "field"
              ? "font-medium text-primary"
              : segment.kind === "operator"
                ? "font-semibold text-foreground underline decoration-primary/60 underline-offset-4"
                : segment.kind === "syntax"
                  ? "text-primary"
                  : segment.kind === "quoted"
                    ? "text-success"
                    : "text-muted-foreground"
          }
        >
          {segment.text}
        </span>
      ))}
    </div>
  );
}

function CatalogQlReference({
  fieldsLabel,
  operatorsLabel,
  literalHint,
}: {
  fieldsLabel: string;
  operatorsLabel: string;
  literalHint: string;
}) {
  return (
    <div className="flex min-w-0 flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
      <QlTokenGroup label={fieldsLabel} tokens={CATALOG_QL_FIELDS} accent />
      <QlTokenGroup
        label={operatorsLabel}
        tokens={[":", ...CATALOG_QL_OPERATORS, "NOT IN", "( )"]}
      />
      <span>{literalHint}</span>
    </div>
  );
}

function QlTokenGroup({
  label,
  tokens,
  accent = false,
}: {
  label: string;
  tokens: readonly string[];
  accent?: boolean;
}) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <span>{label}</span>
      {tokens.map((token) => (
        <code
          key={token}
          className={`rounded-sm bg-muted px-1.5 py-0.5 ${accent ? "text-primary" : "text-foreground"}`}
        >
          {token}
        </code>
      ))}
    </span>
  );
}
