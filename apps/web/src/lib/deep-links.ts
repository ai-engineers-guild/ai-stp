/**
 * Pure deep-link grammar consumer (SPEC-030, ADR-0064, SPEC-047 REQ-4703).
 * Performs no catalog lookup and does not treat a URL as an existence proof.
 */

const ULID_BODY = "[0-7][0-9A-HJKMNP-TV-Z]{25}";
const VERSION_RE = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;
const PREFIX_BY_KIND = {
  component: "component",
  setup: "setup",
  publisher: "account",
} as const;
const COLLECTION_BY_KIND = {
  component: "components",
  setup: "setups",
} as const;

export type DeepLinkKind = keyof typeof PREFIX_BY_KIND;
export type DeepLinkLocale = "ru" | "en";
export type DeepLinkIntent = "view" | "report";

export type DeepLinkTarget = {
  grammar_version: 1;
  kind: DeepLinkKind;
  stable_id: string;
  version: string | null;
  locale: DeepLinkLocale;
  intent: DeepLinkIntent;
};

export type DeepLinkView = {
  schema_version: 1;
  target: DeepLinkTarget;
  web_url: string;
  cli_argv: string[];
  cli_command: string;
};

export const DEFAULT_LOCALE: DeepLinkLocale = "ru";

export class DeepLinkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DeepLinkError";
  }
}

function idPattern(prefix: string): RegExp {
  return new RegExp(`^${prefix}_${ULID_BODY}$`);
}

function assertTarget(target: DeepLinkTarget): void {
  const prefix = PREFIX_BY_KIND[target.kind];
  if (!idPattern(prefix).test(target.stable_id)) {
    throw new DeepLinkError(`stable_id must use the ${prefix}_ canonical form`);
  }
  if (target.kind === "publisher") {
    if (target.version !== null) {
      throw new DeepLinkError("publisher links do not have a version");
    }
    if (target.intent !== "view") {
      throw new DeepLinkError("publisher links support only the view intent");
    }
    return;
  }
  if (target.version !== null && !VERSION_RE.test(target.version)) {
    throw new DeepLinkError("version must use canonical X.Y notation");
  }
  if (target.intent === "report" && target.version === null) {
    throw new DeepLinkError("report intent requires an exact version");
  }
}

function splitBase(value: string): { scheme: string; netloc: string; path: string } {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new DeepLinkError("platform base must be an absolute HTTP(S) URL");
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new DeepLinkError("platform base must be an absolute HTTP(S) URL");
  }
  if (!parsed.hostname) {
    throw new DeepLinkError("platform base must be an absolute HTTP(S) URL");
  }
  if (parsed.username || parsed.password) {
    throw new DeepLinkError("platform base must carry no credentials");
  }
  if (parsed.search || parsed.hash) {
    throw new DeepLinkError("platform base must carry no query or fragment");
  }
  if (parsed.pathname.includes("%") || parsed.pathname.includes("\\")) {
    throw new DeepLinkError("platform base path must use canonical path segments");
  }
  const segments = parsed.pathname.split("/").filter(Boolean);
  if (segments.some((segment) => segment === "." || segment === "..")) {
    throw new DeepLinkError("platform base path must contain no traversal segments");
  }
  return {
    scheme: parsed.protocol.replace(":", ""),
    netloc: parsed.host,
    path: parsed.pathname.replace(/\/$/, ""),
  };
}

function routeFor(target: DeepLinkTarget): string {
  if (target.kind === "publisher") {
    return `${target.locale}/publishers/${target.stable_id}`;
  }
  const collection = COLLECTION_BY_KIND[target.kind];
  let route = `${target.locale}/catalog/${collection}/${target.stable_id}`;
  if (target.version !== null) {
    route = `${route}/versions/${target.version}`;
  }
  return route;
}

export function canonicalArgv(target: DeepLinkTarget): string[] {
  const argv = ["ai-stp", "link", "web", "--kind", target.kind, "--id", target.stable_id];
  if (target.version !== null) {
    argv.push("--version", target.version);
  }
  argv.push("--locale", target.locale);
  if (target.intent === "report") {
    argv.push("--report");
  }
  argv.push("--json");
  return argv;
}

export function normalizeTarget(input: {
  kind: DeepLinkKind;
  stable_id: string;
  version?: string | null;
  locale?: DeepLinkLocale;
  intent?: DeepLinkIntent;
}): DeepLinkTarget {
  const target: DeepLinkTarget = {
    grammar_version: 1,
    kind: input.kind,
    stable_id: input.stable_id,
    version: input.version ?? null,
    locale: input.locale ?? DEFAULT_LOCALE,
    intent: input.intent ?? "view",
  };
  assertTarget(target);
  return target;
}

export function buildDeepLink(platformBase: string, target: DeepLinkTarget): DeepLinkView {
  assertTarget(target);
  const base = splitBase(platformBase);
  const route = routeFor(target);
  const path = base.path ? `${base.path}/${route}` : `/${route}`;
  const fragment = target.intent === "report" ? "#report" : "";
  const webUrl = `${base.scheme}://${base.netloc}${path}${fragment}`;
  const argv = canonicalArgv(target);
  return {
    schema_version: 1,
    target,
    web_url: webUrl,
    cli_argv: argv,
    cli_command: argv.join(" "),
  };
}

function relativePath(basePath: string, candidatePath: string): string {
  const prefix = basePath.replace(/\/$/, "");
  let relative: string;
  if (prefix) {
    const expected = `${prefix}/`;
    if (!candidatePath.startsWith(expected)) {
      throw new DeepLinkError("deep-link URL is outside the configured platform base path");
    }
    relative = candidatePath.slice(expected.length);
  } else {
    relative = candidatePath.replace(/^\//, "");
  }
  if (!relative || relative.startsWith("/") || relative.endsWith("/")) {
    throw new DeepLinkError("deep-link URL path is not canonical");
  }
  return relative;
}

function parseCandidate(webUrl: string): URL {
  try {
    return new URL(webUrl);
  } catch {
    throw new DeepLinkError("deep-link URL does not match the canonical grammar");
  }
}

function parseRoute(segments: string[]): {
  kind: DeepLinkKind;
  stableId: string;
  version: string | null;
} {
  if (segments.length === 3 && segments[1] === "publishers") {
    return { kind: "publisher", stableId: segments[2] ?? "", version: null };
  }
  if ((segments.length === 4 || segments.length === 6) && segments[1] === "catalog") {
    const collection = segments[2];
    const kind: DeepLinkKind =
      collection === "components" ? "component" : collection === "setups" ? "setup" : "publisher";
    if (kind === "publisher") {
      throw new DeepLinkError("deep-link URL uses an unsupported catalog collection");
    }
    if (segments.length === 6 && segments[4] !== "versions") {
      throw new DeepLinkError("deep-link URL has a non-canonical version route");
    }
    return {
      kind,
      stableId: segments[3] ?? "",
      version: segments.length === 6 ? (segments[5] ?? null) : null,
    };
  }
  throw new DeepLinkError("deep-link URL does not match the canonical grammar");
}

export function parseDeepLink(platformBase: string, webUrl: string): DeepLinkTarget {
  const base = splitBase(platformBase);
  const candidate = parseCandidate(webUrl);
  if (candidate.username || candidate.password) {
    throw new DeepLinkError("deep-link URL must carry no credentials");
  }
  if (candidate.search) {
    throw new DeepLinkError("deep-link URL must carry no query");
  }
  if (candidate.protocol.replace(":", "") !== base.scheme || candidate.host !== base.netloc) {
    throw new DeepLinkError("deep-link URL must use the configured platform origin");
  }
  const path = relativePath(base.path, candidate.pathname);
  if (path.includes("%") || path.includes("\\")) {
    throw new DeepLinkError("deep-link URL must use canonical unescaped path segments");
  }
  const segments = path ? path.split("/") : [];
  if (segments.length < 3) {
    throw new DeepLinkError("deep-link URL does not match the canonical grammar");
  }
  const locale = segments[0];
  if (locale !== "ru" && locale !== "en") {
    throw new DeepLinkError("deep-link URL uses an unsupported locale");
  }
  const route = parseRoute(segments);
  const fragment = candidate.hash.replace(/^#/, "");
  let intent: DeepLinkIntent = "view";
  if (fragment) {
    if (fragment !== "report" || route.kind === "publisher" || route.version === null) {
      throw new DeepLinkError("deep-link URL uses an unsupported fragment");
    }
    intent = "report";
  }
  return normalizeTarget({
    kind: route.kind,
    stable_id: route.stableId,
    version: route.version,
    locale,
    intent,
  });
}
