"use server";

import { setCatalogReaction } from "@/lib/api/reactions";

export async function updateCatalogReaction(
  objectKind: "component" | "setup",
  stableId: string,
  liked: boolean,
) {
  return setCatalogReaction(objectKind, stableId, liked);
}
