import type { ComponentSummary, SetupSummary } from "@/lib/api/generated/types.gen";

import { privateApiRequest } from "./http";

export type CatalogReactionState = {
  schema_version: 1;
  liked: boolean;
  likes_count: number;
};

export type CatalogReactionList = {
  schema_version: 1;
  items: Array<{
    object_kind: "component" | "setup";
    summary: ComponentSummary | SetupSummary;
  }>;
};

export function listCatalogReactions(sessionToken?: string): Promise<CatalogReactionList> {
  return privateApiRequest("/v1/account/catalog-reactions", sessionToken ? { sessionToken } : {});
}

export function setCatalogReaction(
  objectKind: "component" | "setup",
  stableId: string,
  liked: boolean,
): Promise<CatalogReactionState> {
  return privateApiRequest(
    `/v1/account/catalog-reactions/${objectKind}/${encodeURIComponent(stableId)}`,
    {
      method: liked ? "PUT" : "DELETE",
    },
  );
}
