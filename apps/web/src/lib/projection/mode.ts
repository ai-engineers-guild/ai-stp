import { headers } from "next/headers";

export type Projection = "human" | "machine";

const PROJECTION_HEADER = "x-projection";
const PATHNAME_HEADER = "x-pathname";

export async function readProjection(): Promise<Projection> {
  const headersList = await headers();
  const val = headersList.get(PROJECTION_HEADER);
  return val === "machine" ? "machine" : "human";
}

/** Canonical pathname (locale-prefixed, without /ai) as set by middleware. */
export async function readCanonicalPathname(): Promise<string | null> {
  const headersList = await headers();
  return headersList.get(PATHNAME_HEADER);
}

// Re-export pure path helpers so server modules keep a single import site.
export { pairedPath, pathWithoutLocale, projectedHref } from "@/lib/projection/paths";
