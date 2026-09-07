import { Badge } from "@/components/atoms/badge";
import type { SetupFamilyPublic } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";

export type SetupFamilyLabels = {
  heading: string;
  summary: string;
  members: string;
  baseline: string;
  alignment: string;
  current: string;
  aligned: string;
  alignedHint: string;
  diverged: string;
  divergedHint: string;
  unknown: string;
  unknownHint: string;
  missing: string;
  missingHint: string;
  version: string;
  harness: string;
  portedFrom: string;
  browseFamily: string;
};

export function setupFamilyLabels(t: (key: string) => string): SetupFamilyLabels {
  return {
    heading: t("familyHeading"),
    summary: t("familySummary"),
    members: t("familyMembers"),
    baseline: t("familyBaseline"),
    alignment: t("familyAlignment"),
    current: t("currentSetup"),
    aligned: t("alignmentAligned"),
    alignedHint: t("alignmentAlignedHint"),
    diverged: t("alignmentDiverged"),
    divergedHint: t("alignmentDivergedHint"),
    unknown: t("alignmentUnknown"),
    unknownHint: t("alignmentUnknownHint"),
    missing: t("alignmentMissing"),
    missingHint: t("alignmentMissingHint"),
    version: t("version"),
    harness: t("harness"),
    portedFrom: t("portedFrom"),
    browseFamily: t("browseFamily"),
  };
}

export function SetupFamilyBlock({
  family,
  currentStableId,
  labels,
}: {
  family: SetupFamilyPublic | null;
  currentStableId: string;
  labels: SetupFamilyLabels;
}) {
  if (!family || family.members.length === 0) return null;

  const ordered = [...family.members].sort((left, right) => {
    if (left.stable_id === currentStableId) return -1;
    if (right.stable_id === currentStableId) return 1;
    return left.harness_id.localeCompare(right.harness_id);
  });

  return (
    <section
      data-ui={UI.catalog.setupFamily}
      aria-labelledby="setup-family-heading"
      className="border-border min-w-0 space-y-4 rounded-lg border p-4"
    >
      <div className="space-y-1">
        <h2 id="setup-family-heading" className="font-semibold">
          {labels.heading}
        </h2>
        <p className="text-muted-foreground text-sm">{labels.summary}</p>
        <p className="text-sm">
          {family.name} · {labels.members}: {family.members.length}
        </p>
        {family.current_member ? (
          <p className="text-sm">
            {labels.harness}: {family.current_member.harness_id}
          </p>
        ) : null}
        <p className="text-muted-foreground text-sm">
          {labels.baseline}: {family.baseline.stable_id}@{family.baseline.version}
        </p>
      </div>
      <ul className="divide-border border-border divide-y overflow-hidden rounded-md border">
        {ordered.map((member) => {
          const current = member.stable_id === currentStableId;
          const href = member.exact_version
            ? `/catalog/setups/${member.stable_id}/versions/${member.exact_version}`
            : `/catalog/setups/${member.stable_id}`;
          const alignment = alignmentCopy(member.alignment, labels);
          return (
            <li key={member.stable_id} className="space-y-2 p-3">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                {current ? (
                  <span className="font-medium">{member.stable_id}</span>
                ) : (
                  <Link
                    href={href}
                    className="font-medium underline underline-offset-4"
                    prefetch={false}
                  >
                    {member.stable_id}
                  </Link>
                )}
                <Badge variant="outline">{member.harness_id}</Badge>
                {current ? <Badge variant="secondary">{labels.current}</Badge> : null}
                {member.latest_version ? (
                  <Badge variant="outline">
                    {labels.version} {member.latest_version}
                  </Badge>
                ) : null}
              </div>
              <p className="text-sm">
                {labels.alignment}: {alignment.label}
              </p>
              <p className="text-muted-foreground text-xs">{alignment.hint}</p>
              {member.ported_from ? (
                <p className="text-muted-foreground text-xs">
                  {labels.portedFrom}: {member.ported_from.stable_id}@{member.ported_from.version}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
      <p>
        <Link
          href={`/catalog?resource=setups&family_id=${encodeURIComponent(family.family_id)}`}
          className="text-sm underline underline-offset-4"
          prefetch={false}
        >
          {labels.browseFamily}
        </Link>
      </p>
    </section>
  );
}

function alignmentCopy(
  state: SetupFamilyPublic["members"][number]["alignment"],
  labels: SetupFamilyLabels,
): { label: string; hint: string } {
  if (state === "aligned") return { label: labels.aligned, hint: labels.alignedHint };
  if (state === "diverged") return { label: labels.diverged, hint: labels.divergedHint };
  if (state === "missing") return { label: labels.missing, hint: labels.missingHint };
  return { label: labels.unknown, hint: labels.unknownHint };
}
