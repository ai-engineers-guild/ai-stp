import { assert } from "vitest";

/** Fail at a missing fixture value before checking the behavior that needs it. */
export function required<T>(value: T): NonNullable<T> {
  assert(
    value !== null && value !== undefined,
    "Required fixture value is absent",
  );
  return value;
}
