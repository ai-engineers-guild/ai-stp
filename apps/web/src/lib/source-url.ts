import type { GitSource } from "@/lib/api/generated/types.gen";

const GITHUB_HOST = "github.com";
const EXACT_COMMIT = /^[0-9a-f]{40}$/i;

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
