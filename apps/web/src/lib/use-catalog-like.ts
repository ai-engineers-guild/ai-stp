"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { updateCatalogReaction } from "@/lib/actions/catalog-reactions";

export type LikeState = {
  liked: boolean;
  count: number;
  pending: boolean;
  toggle: () => void;
};

/** Shared like-toggle state: server-confirmed liked/count, pending guard. */
export function useCatalogLike(props: {
  stableId: string;
  objectKind?: "component" | "setup";
  likesCount?: number;
  initiallyLiked?: boolean;
  labels: { like: string };
}): LikeState {
  const [liked, setLiked] = useState(props.initiallyLiked ?? false);
  const [count, setCount] = useState(props.likesCount ?? 0);
  const [pending, startTransition] = useTransition();
  const objectKind = props.objectKind ?? "component";
  const likeLabel = props.labels.like;
  const stableId = props.stableId;

  function toggle() {
    const next = !liked;
    startTransition(async () => {
      try {
        const state = await updateCatalogReaction(objectKind, stableId, next);
        setLiked(state.liked);
        setCount(state.likes_count);
      } catch {
        toast.error(likeLabel);
      }
    });
  }

  return { liked, count, pending, toggle };
}
