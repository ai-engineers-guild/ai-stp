/** Harnesses a catalog card or detail should show.

 A component or setup passport may name several projections. Empty
 `latest_harness_ids` falls back to the primary `latest_harness_id` so older
 projections stay renderable. Component version passports name harnesses on
 adaptations, not a flat `harness_id`.
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

type FlatHarnessPassport = {
  harness_id: string;
  harness_ids?: ReadonlyArray<string> | null;
};

type AdaptedHarnessPassport = {
  origin_harness_id?: string | null;
  adaptations: ReadonlyArray<{ harness_id: string }>;
};

export function namedPassportHarnesses(
  passport: FlatHarnessPassport | AdaptedHarnessPassport,
): string[] {
  if ("adaptations" in passport) {
    const fromAdaptations = uniqueInOrder(passport.adaptations.map((item) => item.harness_id));
    if (fromAdaptations.length > 0) {
      return fromAdaptations;
    }
    return passport.origin_harness_id ? [passport.origin_harness_id] : [];
  }
  return namedHarnesses({
    latest_harness_id: passport.harness_id,
    ...(passport.harness_ids === undefined ? {} : { latest_harness_ids: passport.harness_ids }),
  });
}

type FlatOsPassport = {
  supported_os?: ReadonlyArray<string> | null;
};

type AdaptedOsPassport = {
  adaptations: ReadonlyArray<{
    scope_adaptations?: ReadonlyArray<{
      supported_os?: ReadonlyArray<string> | null;
    }>;
  }>;
};

export function namedOperatingSystems(passport: FlatOsPassport | AdaptedOsPassport): string[] {
  if ("adaptations" in passport) {
    return uniqueInOrder(
      passport.adaptations.flatMap((adaptation) =>
        (adaptation.scope_adaptations ?? []).flatMap((scope) => scope.supported_os ?? []),
      ),
    );
  }
  return passport.supported_os ? Array.from(passport.supported_os) : [];
}

type FlatProjectionPassport = {
  projection_kind: string;
};

type AdaptedProjectionPassport = {
  adaptations: ReadonlyArray<{
    scope_adaptations?: ReadonlyArray<{
      projection_kind?: string | null;
    }>;
  }>;
};

export function namedProjectionKinds(
  passport: FlatProjectionPassport | AdaptedProjectionPassport,
): string[] {
  if ("adaptations" in passport) {
    return uniqueInOrder(
      passport.adaptations.flatMap((adaptation) =>
        (adaptation.scope_adaptations ?? []).flatMap((scope) =>
          scope.projection_kind ? [scope.projection_kind] : [],
        ),
      ),
    );
  }
  return [passport.projection_kind];
}

function uniqueInOrder(values: ReadonlyArray<string>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    if (!seen.has(value)) {
      seen.add(value);
      result.push(value);
    }
  }
  return result;
}
