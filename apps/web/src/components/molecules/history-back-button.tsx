"use client";

import { useRouter } from "next/navigation";

import { Button } from "@/components/atoms/button";
import { Icon } from "@/theme";

export function HistoryBackButton({ label, fallback }: { label: string; fallback: string }) {
  const router = useRouter();

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={() => {
        if (window.history.length > 1) router.back();
        else router.push(fallback);
      }}
    >
      <Icon name="arrowLeft" size="sm" />
      {label}
    </Button>
  );
}
