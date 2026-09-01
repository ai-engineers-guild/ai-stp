import { Badge } from "@/components/atoms/badge";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { safetyCheckName } from "@/components/molecules/safety-checks-summary";
import { StatePanel } from "@/components/molecules/state-panel";
import type {
  SetupComponentChecks,
  SetupVersionPassport,
  ComponentType,
} from "@/lib/api/generated/types.gen";
import type { SetupContextBudget } from "@/lib/api/catalog";
import { Link } from "@/lib/i18n/navigation";
import { isComponentType } from "@/lib/projection/inventory";
import { ComponentTypeIcon } from "@/theme/component-types";

export type CatalogComponentPresentation = {
  stableId: string;
  version: string;
  componentType: ComponentType;
  ownerId: string;
  authorName?: string | null | undefined;
  sourceUrl?: string | null | undefined;
};

export function SetupComposition({
  passport,
  components,
  catalogComponents,
  setupAuthor,
  budget,
  t,
}: {
  passport: SetupVersionPassport;
  components: SetupComponentChecks[];
  catalogComponents: CatalogComponentPresentation[];
  setupAuthor: { accountId: string; displayName?: string | null | undefined };
  budget: SetupContextBudget | null;
  t: (key: string) => string;
}) {
  const checksByRef = new Map(
    components.map((item) => [`${item.stable_id}@${item.version}`, item]),
  );
  const catalogByRef = new Map(
    catalogComponents.map((item) => [`${item.stableId}@${item.version}`, item]),
  );
  const presentations = componentPresentations(passport);
  const tokensByRef = new Map(
    (budget?.components ?? []).map((item) => [
      `${item.component.stable_id}@${item.component.version}`,
      item,
    ]),
  );
  return (
    <DetailAccordion title={t("composition")} summary={t("compositionDescription")}>
      {passport.components.length ? (
        <ul className="divide-border border-border divide-y rounded-lg border">
          {passport.components.map(
            // eslint-disable-next-line complexity -- one row joins optional catalog, source, scan, and budget evidence
            (ref) => {
              const key = `${ref.stable_id}@${ref.version}`;
              const component = checksByRef.get(key);
              const catalog = catalogByRef.get(key);
              const presentation = presentations.get(key);
              const embedded = component?.embedded ?? presentation?.embedded ?? false;
              const componentType =
                presentation?.componentType ?? catalog?.componentType ?? "setting";
              const name = component?.name ?? presentation?.name ?? ref.stable_id;
              const sourceUrl =
                catalog?.sourceUrl ?? sourceCoordinateUrl(component?.source_coordinate);
              const author = embedded
                ? setupAuthor
                : {
                    accountId: catalog?.ownerId ?? null,
                    displayName: catalog?.authorName,
                  };
              const measurement = tokensByRef.get(key);
              return (
                <li key={key} className="p-4 sm:p-5">
                  <div className="flex items-start gap-3">
                    <ComponentTypeIcon type={componentType} compact />
                    <div className="min-w-0 flex-1 space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        {embedded ? (
                          <span className="font-medium break-words">{name}</span>
                        ) : (
                          <Link
                            href={`/catalog/components/${ref.stable_id}`}
                            className="font-medium break-words underline underline-offset-4"
                          >
                            {name}
                          </Link>
                        )}
                        <Badge variant="secondary">{componentType}</Badge>
                        <Badge variant="outline">
                          {t("version")} {ref.version}
                        </Badge>
                        <Badge variant="outline">
                          {embedded ? t("embeddedSnapshot") : t("catalogComponent")}
                        </Badge>
                      </div>
                      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                        <div>
                          <dt className="text-muted-foreground">{t("componentAuthor")}</dt>
                          <dd>
                            {author.accountId ? (
                              <Link
                                href={`/publishers/${author.accountId}`}
                                className="underline underline-offset-4"
                              >
                                {author.displayName || author.accountId}
                              </Link>
                            ) : (
                              <span className="text-muted-foreground">{t("noneListed")}</span>
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">{t("componentSource")}</dt>
                          <dd>
                            {sourceUrl ? (
                              <a
                                href={sourceUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="break-all underline underline-offset-4"
                              >
                                {sourceLabel(sourceUrl)}
                              </a>
                            ) : (
                              <span className="text-muted-foreground">{t("noneListed")}</span>
                            )}
                          </dd>
                        </div>
                      </dl>
                      <SafetySummary component={component} t={t} />
                      <p className="text-muted-foreground text-sm">
                        {measurement?.tokens === null
                          ? t("contextBudgetError")
                          : measurement
                            ? `${measurement.tokens} ${t("contextBudgetTokens")} · ${measurement.loading === "always" ? t("contextBudgetAlways") : t("contextBudgetConditional")}`
                            : t("contextBudgetRuntimeDerived")}
                      </p>
                      {embedded ? (
                        <p className="text-muted-foreground text-xs">{t("embeddedSnapshotHint")}</p>
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            },
          )}
        </ul>
      ) : (
        <StatePanel kind="empty" title={t("noneListed")} />
      )}
    </DetailAccordion>
  );
}

function SafetySummary({
  component,
  t,
}: {
  component: SetupComponentChecks | undefined;
  t: (key: string) => string;
}) {
  if (!component || component.checks.length === 0) {
    return <Badge variant="outline">{t("safetyNoScan")}</Badge>;
  }
  const countable = component.checks.filter(
    (check) => check.result !== "not_applicable" && check.result !== "skipped",
  );
  const passed = countable.filter((check) => check.result === "passed").length;
  const failed = countable.filter((check) => check.result === "failed").length;
  const warning = countable.filter((check) => check.result === "warning").length;
  const notRun = countable.filter((check) => check.result === "not_run").length;
  const requiredPassed = component.digest_matches && !component.failed_mandatory;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant={requiredPassed ? "success" : "warning"}>
          {requiredPassed ? t("requiredChecksPassed") : t("requiredChecksFailed")}
        </Badge>
        <span className="font-mono tabular-nums">
          {passed}/{countable.length} {t("safetyChecksComplete")}
        </span>
        {failed ? (
          <Badge variant="warning">
            {t("safetyFailed")}: {failed}
          </Badge>
        ) : null}
        {warning ? (
          <Badge variant="outline">
            {t("safetyWarning")}: {warning}
          </Badge>
        ) : null}
        {notRun ? (
          <Badge variant="outline">
            {t("safetyNotRun")}: {notRun}
          </Badge>
        ) : null}
      </div>
      <details className="group">
        <summary className="focus-visible:ring-ring w-fit cursor-pointer text-sm underline underline-offset-4 focus-visible:rounded-sm focus-visible:ring-2 focus-visible:outline-none">
          {t("reviewChecks")}
        </summary>
        <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
          {component.checks.map((check) => (
            <li
              key={`${check.check_id}-${check.source}`}
              className="flex items-center gap-2 text-sm"
            >
              <Badge variant={check.result === "failed" ? "warning" : "outline"}>
                {setupCheckResultLabel(check.result, t)}
              </Badge>
              <span>{safetyCheckName(check.check_id)}</span>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function componentPresentations(passport: SetupVersionPassport) {
  const output = new Map<
    string,
    { name: string; componentType: ComponentType; embedded: boolean }
  >();
  const fact = passport.facts.component_presentations?.value;
  if (!Array.isArray(fact)) return output;
  for (const raw of fact) {
    if (!raw || typeof raw !== "object") continue;
    const item = raw as Record<string, unknown>;
    if (typeof item.stable_id !== "string" || typeof item.version !== "string") continue;
    output.set(`${item.stable_id}@${item.version}`, {
      name: typeof item.name === "string" ? item.name : item.stable_id,
      componentType:
        typeof item.component_type === "string" && isComponentType(item.component_type)
          ? item.component_type
          : "setting",
      embedded: item.embedded === true,
    });
  }
  return output;
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

function sourceLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function setupCheckResultLabel(result: string, t: (key: string) => string): string {
  if (result === "passed") return t("safetyResultPassed");
  if (result === "failed") return t("safetyResultFailed");
  if (result === "warning") return t("safetyResultWarning");
  if (result === "not_applicable" || result === "skipped") {
    return t("safetyResultNotApplicable");
  }
  return t("safetyResultNotRun");
}
