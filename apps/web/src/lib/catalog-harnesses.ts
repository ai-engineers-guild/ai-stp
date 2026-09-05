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

export type ComponentPassportCompatibility = {
  adaptations?: ReadonlyArray<{
    harness_id: string;
    scope_adaptations?: ReadonlyArray<{
      projection_kind?: string | null;
      supported_os?: ReadonlyArray<string> | null;
    }>;
  }>;
  origin_harness_id?: string | null;
  harness_id?: string;
  harness_ids?: ReadonlyArray<string> | null;
  projection_kind?: string;
  supported_os?: ReadonlyArray<string> | null;
};

export function namedPassportHarnesses(passport: ComponentPassportCompatibility): string[] {
  if (passport.adaptations) {
    const fromAdaptations = uniqueInOrder(
      passport.adaptations.map((adaptation) => adaptation.harness_id),
    );
    if (fromAdaptations.length > 0) return fromAdaptations;
    return passport.origin_harness_id ? [passport.origin_harness_id] : [];
  }
  if (passport.harness_id) {
    return namedHarnesses({
      latest_harness_id: passport.harness_id,
      ...(passport.harness_ids === undefined ? {} : { latest_harness_ids: passport.harness_ids }),
    });
  }
  return [];
}

export function componentOperatingSystems(passport: ComponentPassportCompatibility): string[] {
  if (passport.adaptations) {
    return uniqueInOrder(
      passport.adaptations.flatMap((adaptation) =>
        (adaptation.scope_adaptations ?? []).flatMap((scope) => scope.supported_os ?? []),
      ),
    );
  }
  return passport.supported_os ? Array.from(passport.supported_os) : [];
}

export function componentPassportPrimary(passport: ComponentPassportCompatibility) {
  const adaptation = passport.adaptations?.[0];
  return {
    harnessId: adaptation?.harness_id ?? passport.harness_id,
    projectionKind: adaptation?.scope_adaptations?.[0]?.projection_kind ?? passport.projection_kind,
  };
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
