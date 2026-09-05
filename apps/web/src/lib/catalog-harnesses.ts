/** Harnesses a catalog card or detail should show.

 A component or setup passport may name several projections. Empty
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

export type ComponentPassportCompatibility = {
  adaptations?: ReadonlyArray<{
    harness_id: string;
    scope_adaptations: ReadonlyArray<{
      projection_kind?: string;
      supported_os?: ReadonlyArray<string>;
    }>;
  }>;
  harness_id?: string;
  harness_ids?: ReadonlyArray<string> | null;
  projection_kind?: string;
  supported_os?: ReadonlyArray<string> | null;
};

export function namedPassportHarnesses(passport: ComponentPassportCompatibility): string[] {
  if (passport.adaptations) return passport.adaptations.map((adaptation) => adaptation.harness_id);
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
    return Array.from(
      new Set(
        passport.adaptations.flatMap((adaptation) =>
          adaptation.scope_adaptations.flatMap((scope) => scope.supported_os ?? []),
        ),
      ),
    );
  }
  return passport.supported_os ? Array.from(passport.supported_os) : [];
}

export function componentPassportPrimary(passport: ComponentPassportCompatibility) {
  const adaptation = passport.adaptations?.[0];
  return {
    harnessId: adaptation?.harness_id ?? passport.harness_id,
    projectionKind: adaptation?.scope_adaptations[0]?.projection_kind ?? passport.projection_kind,
  };
}

export function namedOperatingSystems(passport: {
  supported_os?: ReadonlyArray<string> | null;
}): string[] {
  return passport.supported_os ? Array.from(passport.supported_os) : [];
}
