export type FieldErrors = Record<string, string>;

/** Convert API/Pydantic paths to the names used by the shared editor fields. */
export function normalizeFieldPath(value: string): string {
  return value
    .trim()
    .replace(/^(?:body\.)?fields\./, "")
    .replace(/^body\./, "")
    .replace(/\[(\d+)\]/g, ".$1")
    .replace(/^\./, "");
}

function pathFromValue(value: unknown): string | null {
  if (typeof value === "string") return normalizeFieldPath(value);
  if (
    Array.isArray(value) &&
    value.every((part) => typeof part === "string" || typeof part === "number")
  ) {
    return normalizeFieldPath(value.map(String).join("."));
  }
  return null;
}

function addError(result: FieldErrors, path: unknown, message: unknown, fallback: string) {
  const normalized = pathFromValue(path);
  if (!normalized) return;
  result[normalized] = typeof message === "string" && message.trim() ? message : fallback;
}

function readContainer(value: unknown, result: FieldErrors, fallback: string) {
  if (typeof value === "string") {
    addError(result, value, fallback, fallback);
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      if (typeof item === "string") {
        addError(result, item, fallback, fallback);
      } else if (item && typeof item === "object") {
        const row = item as Record<string, unknown>;
        addError(
          result,
          row.path ?? row.field ?? row.loc ?? row.location,
          row.message ?? row.detail,
          fallback,
        );
      }
    }
    return;
  }
  if (!value || typeof value !== "object") return;
  for (const [path, message] of Object.entries(value as Record<string, unknown>)) {
    if (typeof message === "string") addError(result, path, message, fallback);
    else if (message && typeof message === "object") {
      const row = message as Record<string, unknown>;
      addError(result, path, row.message ?? row.detail, fallback);
    }
  }
}

/** Read the field details emitted by validation errors from all edit APIs. */
export function fieldErrorsFromDetails(
  details: Record<string, unknown>,
  fallback: string,
): FieldErrors {
  const result: FieldErrors = {};
  for (const key of ["field_errors", "fields", "errors"]) {
    readContainer(details[key], result, fallback);
  }
  return result;
}

export function fieldErrorsFromIssues(
  issues: readonly { path: readonly PropertyKey[]; message: string }[],
): FieldErrors {
  const result: FieldErrors = {};
  for (const issue of issues) addError(result, issue.path, issue.message, issue.message);
  return result;
}

export function fieldError(result: FieldErrors, ...paths: string[]): string | undefined {
  return paths.map((path) => result[path]).find(Boolean);
}

export function withoutFieldErrors(result: FieldErrors, prefixes: readonly string[]): FieldErrors {
  return Object.fromEntries(
    Object.entries(result).filter(([path]) => !prefixes.some((prefix) => path.startsWith(prefix))),
  );
}

export function localizeCorporateFieldErrors(
  raw: FieldErrors | undefined,
  messages: {
    displayName: string;
    description: string;
    tooManyLinks: string;
    linkLabel: string;
    linkUrl: string;
    mediaSource: string;
    mediaAlt: string;
  },
): FieldErrors {
  const generic = (message: string) =>
    message === "request validation failed" ||
    message === "invalid corporate profile" ||
    message === "string_too_short";
  return Object.fromEntries(
    Object.entries(raw ?? {}).map(([rawPath, message]) => {
      const path = rawPath === "metadata.name" ? "name" : rawPath;
      if (!generic(message)) return [path, message];
      if (path === "name") return [path, messages.displayName];
      if (path === "description") return [path, messages.description];
      if (path === "links") return [path, messages.tooManyLinks];
      if (path.endsWith(".label")) return [path, messages.linkLabel];
      if (path.startsWith("links.")) return [path, messages.linkUrl];
      if (path.endsWith(".alt")) return [path, messages.mediaAlt];
      if (path.startsWith("media.")) return [path, messages.mediaSource];
      return [path, message];
    }),
  );
}

export function formatCorporateFieldPath(
  path: string,
  labels: {
    displayName: string;
    description: string;
    links: string;
    label: string;
    media: string;
    url: string;
    alt: string;
    kind: string;
  },
): string {
  if (path === "name") return labels.displayName;
  if (path === "description") return labels.description;
  const link = path.match(/^links\.(\d+)\.(label|url)$/);
  if (link)
    return `${labels.links} #${Number(link[1]) + 1} ${link[2] === "label" ? labels.label : labels.url}`;
  const media = path.match(/^media\.(\d+)\.(url|alt|kind)$/);
  if (media) {
    const field = media[2] === "alt" ? labels.alt : media[2] === "kind" ? labels.kind : labels.url;
    return `${labels.media} #${Number(media[1]) + 1} ${field}`;
  }
  return path;
}
