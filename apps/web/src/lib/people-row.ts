/** Embedded controls own their click; the remaining row surface opens details. */
export function isPeopleRowControl(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    target.closest("a, button, input, select, textarea, [role^='menuitem']") !== null
  );
}
