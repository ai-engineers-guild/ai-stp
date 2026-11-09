/** Refuse incomplete offline fixtures before using their dependent values. */
export function required<T>(value: T): NonNullable<T> {
  if (value === null || value === undefined) {
    throw new Error("Required fixture value is absent");
  }
  return value;
}
