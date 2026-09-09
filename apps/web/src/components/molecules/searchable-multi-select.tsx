"use client";

import { useId, useMemo, useRef, useState } from "react";

import { AvatarImage } from "@/components/atoms/avatar-image";
import { Icon } from "@/theme";

type Option = string | { value: string; label: string; avatarUrl?: string | null };

type SearchableMultiSelectProps = {
  name: string;
  label: string;
  searchLabel: string;
  options: readonly Option[];
  selected: readonly string[];
  form?: string;
  onChange?: (values: string[]) => void;
  multiple?: boolean;
  modal?: boolean;
  closeLabel?: string;
  selectionSuffix?: string | undefined;
  emptyHint?: string | undefined;
};

function optionValue(option: Option): string {
  return typeof option === "string" ? option : option.value;
}

function optionLabel(option: Option): string {
  return typeof option === "string" ? option : option.label;
}

function optionAvatar(option: Option): string | null {
  return typeof option === "string" ? null : (option.avatarUrl ?? null);
}

function optionInitials(label: string): string {
  const parts = label.trim().split(/\s+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

/** Form-native searchable multiselect with repeated query parameters. */
// eslint-disable-next-line max-lines-per-function
export function SearchableMultiSelect({
  name,
  label,
  searchLabel,
  options,
  selected,
  form,
  onChange,
  multiple = true,
  modal = false,
  closeLabel = "Close",
  selectionSuffix = "selected",
  emptyHint = "Select one or more options",
}: SearchableMultiSelectProps) {
  const id = useId();
  const titleId = `${id}-title`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [checked, setChecked] = useState<string[]>(() => [...selected]);
  const filtered = useMemo(
    () =>
      options.filter((option) =>
        `${optionLabel(option)} ${optionValue(option)}`
          .toLocaleLowerCase()
          .includes(search.toLocaleLowerCase()),
      ),
    [options, search],
  );

  function toggle(value: string, next: boolean) {
    const updated = multiple
      ? next
        ? [...checked, value]
        : checked.filter((item) => item !== value)
      : next
        ? [value]
        : [];
    setChecked(updated);
    onChange?.(updated);
  }

  function closeDialog() {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
    setOpen(false);
    triggerRef.current?.focus();
  }

  if (modal) {
    return (
      <div className="min-w-0">
        {checked.map((value) => (
          <input key={value} type="hidden" form={form} name={name} value={value} />
        ))}
        <button
          type="button"
          ref={triggerRef}
          aria-haspopup="dialog"
          aria-expanded={open}
          className="border-input bg-background focus-visible:ring-ring flex min-h-11 w-full min-w-0 items-center justify-between gap-3 rounded-sm border px-3 py-2 text-left text-sm focus-visible:ring-2 focus-visible:outline-none"
          onClick={() => {
            const dialog = dialogRef.current;
            if (!dialog) return;
            if (typeof dialog.showModal === "function") dialog.showModal();
            else dialog.setAttribute("open", "");
            setOpen(true);
          }}
        >
          <span className="min-w-0 truncate">
            {label}
            {checked.length > 0 ? ` (${checked.length})` : ""}
          </span>
          <Icon name="chevronDown" size="sm" />
        </button>
        <dialog
          ref={dialogRef}
          aria-labelledby={titleId}
          onCancel={() => {
            setOpen(false);
          }}
          onClose={() => {
            setOpen(false);
            triggerRef.current?.focus();
          }}
          className="border-border bg-popover text-popover-foreground m-auto max-h-[min(42rem,calc(100vh-2rem))] w-[min(34rem,calc(100vw-2rem))] min-w-0 rounded-lg border p-0 shadow-md backdrop:bg-black/60"
        >
          <div className="space-y-4 p-4 sm:p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 id={titleId} className="text-lg font-medium">
                  {label}
                </h2>
                <p className="text-muted-foreground mt-1 text-xs">
                  {checked.length ? `${checked.length} ${selectionSuffix}` : emptyHint}
                </p>
              </div>
              <button
                type="button"
                aria-label={closeLabel}
                className="text-muted-foreground hover:bg-muted focus-visible:ring-ring grid size-9 shrink-0 place-items-center rounded-sm focus-visible:ring-2 focus-visible:outline-none"
                onClick={() => {
                  closeDialog();
                }}
              >
                <Icon name="close" size="sm" />
              </button>
            </div>
            <label htmlFor={id} className="sr-only">
              {searchLabel}
            </label>
            <input
              id={id}
              type="search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
              }}
              placeholder={searchLabel}
              className="border-input bg-background focus-visible:ring-ring h-11 w-full rounded-sm border px-3 text-base focus-visible:ring-2 focus-visible:outline-none sm:text-sm"
            />
            <div
              className="max-h-[min(24rem,50vh)] space-y-1 overflow-y-auto"
              role="group"
              aria-label={label}
            >
              {filtered.map((option) => {
                const value = optionValue(option);
                const text = optionLabel(option);
                return (
                  <label
                    key={value || text}
                    className="hover:bg-muted flex min-h-12 min-w-0 items-center gap-3 rounded-sm px-3 py-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      aria-label={text}
                      checked={checked.includes(value)}
                      onChange={(event) => {
                        toggle(value, event.target.checked);
                      }}
                    />
                    <span className="min-w-0 flex-1 break-words">{text}</span>
                    <AvatarImage
                      src={optionAvatar(option)}
                      width={32}
                      height={32}
                      className="size-8 shrink-0 rounded-full object-cover"
                      fallback={
                        <span className="bg-muted text-muted-foreground grid size-8 shrink-0 place-items-center rounded-full text-[10px] font-medium">
                          {optionInitials(text)}
                        </span>
                      }
                    />
                  </label>
                );
              })}
            </div>
          </div>
        </dialog>
      </div>
    );
  }

  return (
    <details
      name="catalog-filter"
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
        if (!event.currentTarget.open) return;
        document
          .querySelectorAll<HTMLDetailsElement>('details[name="catalog-filter"][open]')
          .forEach((details) => {
            if (details !== event.currentTarget) details.open = false;
          });
      }}
      className="border-border bg-background relative min-w-0 rounded-sm border"
    >
      <summary
        aria-expanded={open}
        className="focus-visible:ring-ring flex min-h-11 min-w-0 cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-sm marker:content-none focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden"
      >
        <span className="min-w-0 truncate">
          {label}
          {checked.length > 0 ? ` (${checked.length})` : ""}
        </span>
        <Icon name={open ? "chevronUp" : "chevronDown"} size="sm" />
      </summary>
      <div className="bg-popover border-border relative z-50 min-w-0 space-y-2 rounded-sm border p-3 shadow-md md:absolute md:top-[calc(100%+0.375rem)] md:right-0 md:left-0">
        <label htmlFor={id} className="sr-only">
          {searchLabel}
        </label>
        <input
          id={id}
          type="search"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
          }}
          placeholder={searchLabel}
          className="border-input bg-background h-11 w-full rounded-sm border px-3 text-base sm:text-sm"
        />
        {checked
          .filter((value) => !filtered.some((option) => optionValue(option) === value))
          .map((value) => (
            <input key={`hidden:${value}`} type="hidden" form={form} name={name} value={value} />
          ))}
        <div className="max-h-56 space-y-1 overflow-y-auto" role="group" aria-label={label}>
          {filtered.map((option) => {
            const value = optionValue(option);
            const text = optionLabel(option);
            return (
              <label
                key={value || text}
                className="hover:bg-muted flex min-h-11 min-w-0 items-center gap-2 rounded-sm px-2 py-2 text-sm"
              >
                <input
                  form={form}
                  type="checkbox"
                  name={name}
                  value={value}
                  checked={checked.includes(value)}
                  onChange={(event) => {
                    toggle(value, event.target.checked);
                  }}
                />
                <span
                  className={
                    typeof option === "string"
                      ? "min-w-0 font-mono text-xs break-all"
                      : "min-w-0 break-words"
                  }
                >
                  {text}
                </span>
              </label>
            );
          })}
        </div>
      </div>
    </details>
  );
}
