"use client";

import { useId, useMemo, useState } from "react";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import {
  completeCatalogQlToken,
  correctCatalogQuery,
  suggestCatalogQlWords,
} from "@/lib/catalog-query-assist";
import { Icon } from "@/theme";

export function CatalogQueryField({
  label,
  placeholder,
  submitLabel,
  defaultValue,
  correctionLabel,
}: {
  label: string;
  placeholder: string;
  submitLabel: string;
  defaultValue: string;
  correctionLabel: string;
}) {
  const listId = useId();
  const [value, setValue] = useState(defaultValue);
  const [activeIndex, setActiveIndex] = useState(-1);
  const correction = useMemo(() => correctCatalogQuery(value), [value]);
  const suggestions = useMemo(() => suggestCatalogQlWords(value), [value]);

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
            className="text-muted-foreground pointer-events-none absolute top-3 left-3"
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
            <ul
              id={listId}
              role="listbox"
              className="border-border bg-popover absolute z-10 mt-1 w-full rounded-sm border py-1 shadow-sm"
            >
              {suggestions.map((word, index) => (
                <li key={word} role="presentation">
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
                    {word}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <Button type="submit" className="min-h-11 w-full sm:w-auto">
          {submitLabel}
        </Button>
      </div>
      <div id="catalog-query-assist" className="min-h-6" aria-live="polite">
        {correction !== value ? (
          <button
            type="button"
            onClick={() => {
              setValue(correction);
            }}
            className="text-muted-foreground hover:text-foreground text-sm underline underline-offset-4"
          >
            {correctionLabel}: <span className="font-mono">{correction}</span>
          </button>
        ) : null}
      </div>
    </div>
  );
}
