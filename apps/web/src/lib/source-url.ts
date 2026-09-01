import type { GitSource } from "@/lib/api/generated/types.gen";

const GITHUB_HOST = "github.com";
const EXACT_COMMIT = /^[0-9a-f]{40}$/i;

export type PublicSourceLink = {
  href: string;
  provider: string;
  exact: boolean;
};

type SourceFacts = {
  source_links?: { value: unknown };
};

function safeSourceUrl(raw: string | undefined): string | null {
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (
      url.protocol !== "https:" ||
      !url.hostname ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    ) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

function sourceProvider(href: string): string {
  const host = new URL(href).hostname.toLowerCase();
  if (host === "github.com") return "GitHub";
  if (host === "pypi.org" || host === "files.pythonhosted.org") return "PyPI";
  if (host === "npmjs.com" || host.endsWith(".npmjs.com") || host === "registry.npmjs.org") {
    return "npm";
  }
  if (host === "crates.io") return "crates.io";
  if (host === "pkg.go.dev" || host === "proxy.golang.org") return "Go";
  if (host === "pub.dev") return "pub.dev";
  return "Source";
}

function githubRepositoryParts(
  source: GitSource | null | undefined,
): { owner: string; name: string } | null {
  if (!source) return null;

  let repository: URL;
  try {
    repository = new URL(source.repository);
  } catch {
    return null;
  }

  if (repository.protocol !== "https:" || repository.hostname !== GITHUB_HOST) return null;
  if (repository.username || repository.password || repository.search || repository.hash)
    return null;

  const segments = repository.pathname.split("/").filter(Boolean);
  if (segments.length !== 2) return null;

  const [owner, rawRepository] = segments;
  const name = rawRepository?.replace(/\.git$/i, "");
  if (!owner || !name) return null;
  return { owner, name };
}

export function githubRepositoryUrl(source: GitSource | null | undefined): string | null {
  const parts = githubRepositoryParts(source);
  if (!parts) return null;
  return `https://${GITHUB_HOST}/${encodeURIComponent(parts.owner)}/${encodeURIComponent(parts.name)}`;
}

export function exactSourceUrl(source: GitSource | null | undefined): string | null {
  if (!source || !EXACT_COMMIT.test(source.commit)) return null;
  const root = githubRepositoryUrl(source);
  if (!root) return null;

  const path = source.path
    .split("/")
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return `${root}/${path ? "tree" : "commit"}/${source.commit}${path ? `/${path}` : ""}`;
}

export function githubSourceUrl(source: GitSource | null | undefined): string | null {
  return exactSourceUrl(source) ?? githubRepositoryUrl(source);
}

export function sourceLinksFor(
  source: GitSource | null | undefined,
  facts?: SourceFacts | null,
): PublicSourceLink[] {
  const declared = facts?.source_links?.value;
  const declaredLinks = Array.isArray(declared)
    ? declared
        .filter((value): value is string => typeof value === "string")
        .map((value) => safeSourceUrl(value))
        .filter((value): value is string => value !== null)
    : [];
  const links = declaredLinks.length
    ? declaredLinks
    : (() => {
        const exact = exactSourceUrl(source);
        const generic = safeSourceUrl(source?.repository);
        return exact ? [exact] : generic ? [generic] : [];
      })();
  return [...new Set(links)].map((href) => ({
    href,
    provider: sourceProvider(href),
    exact: href === exactSourceUrl(source),
  }));
}
