import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { UI } from "@/lib/ui-selectors";

type SearchFieldProps = {
  id: string;
  label: string;
  placeholder: string;
  submitLabel: string;
  defaultValue?: string;
  name?: string;
  helpLabel?: string;
  onHelp?: () => void;
};

/** Labeled search input + submit (primary CTA for the enclosing filter form). */
export function SearchField({
  id,
  label,
  placeholder,
  submitLabel,
  defaultValue,
  name = "q",
  helpLabel,
  onHelp,
}: SearchFieldProps) {
  return (
    <div data-ui={UI.catalog.search} className="flex w-full flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        {helpLabel && onHelp ? (
          <button
            type="button"
            onClick={onHelp}
            className="border-border text-muted-foreground hover:text-foreground inline-flex h-6 w-6 items-center justify-center rounded-full border text-xs"
            aria-label={helpLabel}
          >
            ?
          </button>
        ) : null}
      </div>
      <div className="flex gap-2">
        <Input
          id={id}
          name={name}
          type="search"
          placeholder={placeholder}
          defaultValue={defaultValue}
          className="flex-1"
        />
        <Button type="submit">{submitLabel}</Button>
      </div>
    </div>
  );
}
