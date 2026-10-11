import { Icon } from "@/theme";

/** "?" glyph next to a label; the explanation rides the title for pointer
 * users and an sr-only span for assistive tech. */
export function FieldHint({ text }: { text: string }) {
  return (
    <span className="text-muted-foreground inline-flex align-middle" title={text}>
      <Icon name="help" size="sm" />
      <span className="sr-only">{text}</span>
    </span>
  );
}
