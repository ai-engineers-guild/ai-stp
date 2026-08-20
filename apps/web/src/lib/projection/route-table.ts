import type { MachineDocument } from "@/lib/projection/machine-document";
import type { FeatureKey } from "@/lib/features/definitions";

export type MachineRouteContext = {
  locale: string;
  segments: string[];
  searchParams: Record<string, string | string[] | undefined>;
};

export type MachineRoute = {
  /** Route pattern segments; `:name` matches one segment, `*` matches the rest. */
  pattern: string;
  feature?: FeatureKey;
  resolve: (ctx: MachineRouteContext) => MachineDocument | null | Promise<MachineDocument | null>;
};

/** Does a pattern describe this page path? */
export function matchesPattern(pattern: string, segments: string[]): boolean {
  const parts = pattern.split("/").filter(Boolean);
  if (parts.at(-1) === "*") {
    const head = parts.slice(0, -1);
    return head.every((part, i) => part.startsWith(":") || part === segments[i]);
  }
  if (parts.length !== segments.length) return false;
  return parts.every((part, i) => part.startsWith(":") || part === segments[i]);
}
