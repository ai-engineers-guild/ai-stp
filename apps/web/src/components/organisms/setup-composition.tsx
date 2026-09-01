import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { StatePanel } from "@/components/molecules/state-panel";
import type { SetupComponentChecks, SetupVersionPassport } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";

export function SetupComposition({
  passport,
  components,
  t,
}: {
  passport: SetupVersionPassport;
  components: SetupComponentChecks[];
  t: (key: string) => string;
}) {
  const checksByRef = new Map(
    components.map((item) => [`${item.stable_id}@${item.version}`, item]),
  );
  return (
    <DetailAccordion title={t("composition")} summary={t("compositionDescription")}>
      {passport.components.length ? (
        <ol className="space-y-3">
          {passport.components.map((ref, index) => {
            const component = checksByRef.get(`${ref.stable_id}@${ref.version}`);
            const name = component?.name ?? ref.stable_id;
            const href = component?.embedded
              ? sourceCoordinateUrl(component.source_coordinate)
              : `/catalog/components/${ref.stable_id}`;
            return (
              <li key={`${ref.stable_id}@${ref.version}`} className="flex items-center gap-3">
                <span className="bg-muted grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-semibold">
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  {href && component?.embedded ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm font-medium break-all underline underline-offset-4"
                    >
                      {name}
                    </a>
                  ) : href ? (
                    <Link
                      href={href}
                      className="text-sm font-medium break-all underline underline-offset-4"
                    >
                      {name}
                    </Link>
                  ) : (
                    <span className="text-sm font-medium break-all">{name}</span>
                  )}
                  <p className="text-muted-foreground mt-1 text-sm">
                    {t("pinnedVersion")} {ref.version}
                    {component?.embedded
                      ? ` · ${t("embeddedSnapshot")}`
                      : ` · ${t("catalogComponent")}`}
                  </p>
                  {component?.embedded ? (
                    <p className="text-muted-foreground mt-1 text-xs">
                      {t("embeddedSnapshotHint")}
                    </p>
                  ) : null}
                  {component?.checks.length ? (
                    <ul className="mt-2 flex flex-wrap gap-2">
                      {component.checks.map((check) => (
                        <li key={check.check_id} className="font-mono text-xs">
                          {check.check_id}: {check.result}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <StatePanel kind="empty" title={t("noneListed")} />
      )}
    </DetailAccordion>
  );
}

function sourceCoordinateUrl(coordinate: string | null | undefined): string | null {
  if (!coordinate || coordinate.startsWith("path:")) return null;
  if (coordinate.startsWith("git:https://github.com/")) {
    return coordinate.slice(4).split("@", 1)[0] ?? null;
  }
  const match = /^package:(npm|pypi|crates\.io|go|pub\.dev):(.+)@([^@]+)$/.exec(coordinate);
  if (!match) return null;
  const [, ecosystem, name, version] = match;
  const exactVersion = version?.split(":", 1)[0];
  if (!name || !exactVersion) return null;
  if (ecosystem === "npm") return `https://www.npmjs.com/package/${name}/v/${exactVersion}`;
  if (ecosystem === "pypi") return `https://pypi.org/project/${name}/${exactVersion}/`;
  if (ecosystem === "crates.io") return `https://crates.io/crates/${name}/${exactVersion}`;
  if (ecosystem === "go") return `https://pkg.go.dev/${name}@${exactVersion}`;
  return `https://pub.dev/packages/${name}/versions/${exactVersion}`;
}
