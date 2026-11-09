import { Icon } from "@/theme";

/** "?" glyph next to a label; the explanation rides the title for pointer
 * users and an sr-only span for assistive tech. */
export function FieldHint({ text }: { text: string }) {
  return (
    <span className="inline-flex align-middle text-muted-foreground" title={text}>
      <Icon name="help" size="sm" />
      <span className="sr-only">{text}</span>
    </span>
  );
}
