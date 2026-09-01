import { Badge } from "@/components/atoms/badge";
import { DetailAccordion } from "@/components/molecules/detail-accordion";
import { StatePanel } from "@/components/molecules/state-panel";
import type {
  ComponentType,
  SetupComponentChecks,
  SetupVersionPassport,
} from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";
import { isComponentType } from "@/lib/projection/inventory";
import { ComponentTypeIcon } from "@/theme/component-types";
import { Icon } from "@/theme/icons";

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
  t,
}: {
  passport: SetupVersionPassport;
  components: SetupComponentChecks[];
  catalogComponents: CatalogComponentPresentation[];
  setupAuthor: { accountId: string; displayName?: string | null | undefined };
  t: (key: string) => string;
}) {
  const checksByRef = new Map(
    components.map((item) => [`${item.stable_id}@${item.version}`, item]),
  );
  const catalogByRef = new Map(
    catalogComponents.map((item) => [`${item.stableId}@${item.version}`, item]),
  );
  const presentations = componentPresentations(passport);

  return (
    <DetailAccordion title={t("composition")} summary={t("compositionDescription")}>
      {passport.components.length ? (
        <ul className="divide-border border-border divide-y overflow-hidden rounded-lg border">
          {passport.components.map(
            // One row resolves catalog identity, embedded provenance, and external source display.
            // eslint-disable-next-line complexity
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
                catalog?.sourceUrl ??
                sourceCoordinateUrl(component?.source_coordinate ?? presentation?.sourceCoordinate);
              const identity = embedded
                ? setupAuthor
                : {
                    accountId: catalog?.ownerId ?? "",
                    displayName: catalog?.authorName,
                  };

              return (
                <li key={key} className={embedded ? "bg-muted/20 p-4 sm:p-5" : "p-4 sm:p-5"}>
                  <div className="flex min-w-0 items-start gap-3 sm:gap-4">
                    <ComponentTypeIcon type={componentType} compact />
                    <div className="min-w-0 flex-1">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        {embedded ? (
                          <span className="font-medium [overflow-wrap:anywhere] break-words">
                            {name}
                          </span>
                        ) : (
                          <Link
                            href={`/catalog/components/${ref.stable_id}`}
                            className="font-medium [overflow-wrap:anywhere] break-words underline underline-offset-4"
                          >
                            {name}
                          </Link>
                        )}
                        <Badge variant="outline">{componentType}</Badge>
                        <Badge variant="outline">
                          {t("version")} {ref.version}
                        </Badge>
                        {embedded ? (
                          <Badge variant="secondary">{t("externalComponent")}</Badge>
                        ) : null}
                      </div>

                      <div className="text-muted-foreground mt-2 flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                        <span>
                          {embedded ? t("componentPublisher") : t("componentAuthor")}:{" "}
                          {identity.accountId ? (
                            <Link
                              href={`/publishers/${identity.accountId}`}
                              className="text-foreground underline underline-offset-4"
                            >
                              {identity.displayName || identity.accountId}
                            </Link>
                          ) : (
                            t("noneListed")
                          )}
                        </span>
                        {sourceUrl ? (
                          <a
                            href={sourceUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="text-foreground inline-flex min-w-0 items-center gap-1.5 underline underline-offset-4"
                          >
                            <Icon name={sourceIcon(sourceUrl)} size="sm" />
                            <span className="truncate">{sourceLabel(sourceUrl)}</span>
                          </a>
                        ) : null}
                      </div>
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

function componentPresentations(passport: SetupVersionPassport) {
  const output = new Map<
    string,
    {
      name: string;
      componentType: ComponentType;
      embedded: boolean;
      sourceCoordinate: string | null;
    }
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
      sourceCoordinate: typeof item.source_coordinate === "string" ? item.source_coordinate : null,
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

function sourceIcon(url: string): "github" | "objects" {
  try {
    return new URL(url).hostname === "github.com" ? "github" : "objects";
  } catch {
    return "objects";
  }
}

function sourceLabel(url: string): string {
  try {
    const hostname = new URL(url).hostname.replace(/^www\./, "");
    if (hostname === "npmjs.com") return "npm";
    if (hostname === "pypi.org") return "PyPI";
    if (hostname === "crates.io") return "crates.io";
    if (hostname === "pkg.go.dev") return "Go packages";
    if (hostname === "pub.dev") return "pub.dev";
    if (hostname === "github.com") return "GitHub";
    return hostname;
  } catch {
    return url;
  }
}
