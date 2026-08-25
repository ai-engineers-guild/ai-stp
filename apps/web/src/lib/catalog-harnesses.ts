/** Harnesses a catalog card or detail should show.

A component passport may name several; a setup still has exactly one. Empty
`latest_harness_ids` falls back to the primary `latest_harness_id` so older
projections stay renderable.
*/
export function namedHarnesses(item: {
  latest_harness_id: string;
  latest_harness_ids?: ReadonlyArray<string> | null;
}): string[] {
  const extra = item.latest_harness_ids;
  if (extra && extra.length > 0) {
    return Array.from(extra);
  }
  return [item.latest_harness_id];
}

export function namedPassportHarnesses(passport: {
  harness_id: string;
  harness_ids?: ReadonlyArray<string> | null;
}): string[] {
  return namedHarnesses({
    latest_harness_id: passport.harness_id,
    ...(passport.harness_ids === undefined ? {} : { latest_harness_ids: passport.harness_ids }),
  });
}

export function namedOperatingSystems(passport: {
  supported_os?: ReadonlyArray<string> | null;
}): string[] {
  return passport.supported_os ? Array.from(passport.supported_os) : [];
}
