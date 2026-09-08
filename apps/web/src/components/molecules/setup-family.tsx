import { Badge } from "@/components/atoms/badge";
import { CatalogItemMenu } from "@/components/organisms/catalog-item-menu";
import type { SetupFamilyPublic, SetupRef } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";

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
  setup: string;
  parent: string;
  recast: string;
  moreActions: string;
  copyUrl: string;
  copyCli: string;
  copyId: string;
  copied: string;
  like: string;
  unlike: string;
  report: string;
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
    setup: t("setupKind"),
    parent: t("familyParent"),
    recast: t("familyRecast"),
    moreActions: t("moreActions"),
    copyUrl: t("copyUrl"),
    copyCli: t("copyCli"),
    copyId: t("copyId"),
    copied: t("copied"),
    like: t("likeMenu"),
    unlike: t("unlikeMenu"),
    report: t("reportSetup"),
  };
}

export function SetupFamilyBlock({
  family,
  currentStableId,
  portedFrom,
  labels,
}: {
  family: SetupFamilyPublic | null;
  currentStableId: string;
  portedFrom?: SetupRef | null;
  labels: SetupFamilyLabels;
}) {
  if (!family || family.members.length === 0) return null;

  const parentMember = portedFrom
    ? family.members.find((member) => member.stable_id === portedFrom.stable_id)
    : undefined;
  const parentName = parentMember?.name ?? portedFrom?.stable_id;
  const parentHref = portedFrom
    ? `/catalog/setups/${portedFrom.stable_id}/versions/${portedFrom.version}`
    : null;

  const ordered = [...family.members].sort((left, right) => {
    if (left.stable_id === currentStableId) return -1;
    if (right.stable_id === currentStableId) return 1;
    return left.harness_id.localeCompare(right.harness_id);
  });

  return (
    <section
      data-ui={UI.catalog.setupFamily}
      aria-labelledby="setup-family-heading"
      className="border-border min-w-0 rounded-lg border"
    >
      <details className="group">
        <summary className="focus-visible:ring-ring flex min-h-20 cursor-pointer list-none items-center gap-3 rounded-lg p-4 focus-visible:ring-2 focus-visible:outline-none [&::-webkit-details-marker]:hidden">
          <div className="min-w-0 flex-1 space-y-1">
            <h2 id="setup-family-heading" className="font-semibold">
              {labels.heading}
            </h2>
            <p className="text-muted-foreground text-sm">
              {currentStableId === family.baseline.stable_id ? labels.parent : labels.recast}
              {" · "}
              {labels.members}: {family.members.length}
            </p>
          </div>
          <Icon
            name="chevronDown"
            size="sm"
            className="shrink-0 transition-transform group-open:rotate-180"
          />
        </summary>
        {portedFrom && parentName && parentHref ? (
          <p className="border-border text-muted-foreground border-t px-4 py-3 text-sm">
            {labels.portedFrom}:{" "}
            <Link
              href={parentHref}
              className="text-foreground font-medium underline-offset-4 hover:underline"
              prefetch={false}
            >
              {parentName}
            </Link>
            <span className="text-muted-foreground"> @{portedFrom.version}</span>
          </p>
        ) : null}
        <ul className="divide-border border-border divide-y border-t">
          {ordered.map((member) => {
            const current = member.stable_id === currentStableId;
            const name = member.name;
            const href = member.exact_version
              ? `/catalog/setups/${member.stable_id}/versions/${member.exact_version}`
              : `/catalog/setups/${member.stable_id}`;
            const menuVersion = member.exact_version ?? member.latest_version;
            return (
              <li key={member.stable_id} className="flex min-w-0 items-center gap-2 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <Link
                    href={href}
                    className="font-medium break-words underline-offset-4 hover:underline"
                    prefetch={false}
                  >
                    {name}
                  </Link>
                  <div className="mt-1 flex flex-wrap items-center gap-1">
                    <Badge variant="outline">{labels.setup}</Badge>
                    <Badge variant="secondary">{member.harness_id}</Badge>
                    {member.latest_version ? (
                      <span className="text-muted-foreground text-xs">
                        {labels.version} {member.latest_version}
                      </span>
                    ) : null}
                    {current ? <Badge variant="outline">{labels.current}</Badge> : null}
                  </div>
                </div>
                {menuVersion ? (
                  <CatalogItemMenu
                    kind="setup"
                    stableId={member.stable_id}
                    version={menuVersion}
                    href={href}
                    labels={{
                      more: labels.moreActions,
                      copyUrl: labels.copyUrl,
                      copyCli: labels.copyCli,
                      copyId: labels.copyId,
                      copied: labels.copied,
                      report: labels.report,
                      like: labels.like,
                      unlike: labels.unlike,
                    }}
                  />
                ) : (
                  <Link
                    href={href}
                    aria-label={`${labels.browseFamily}: ${name}`}
                    className="hover:bg-muted focus-visible:ring-ring inline-flex size-11 shrink-0 items-center justify-center rounded-sm focus-visible:ring-2 focus-visible:outline-none"
                    prefetch={false}
                  >
                    <Icon name="moreVertical" size="sm" />
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      </details>
    </section>
  );
}
