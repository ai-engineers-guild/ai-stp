"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";

type ErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function LocaleError({ error, reset }: ErrorProps) {
  const t = useTranslations("errors");
  const tc = useTranslations("common");
  const isChunkLoadError =
    error.name === "ChunkLoadError" || /(?:Failed to load|Loading) chunk/i.test(error.message);
  return (
    <StatePanel
      kind="error"
      title={t("errorTitle")}
      description={t("errorBody")}
      action={
        <Button
          type="button"
          onClick={() => {
            if (isChunkLoadError) {
              window.location.reload();
              return;
            }
            reset();
          }}
        >
          {tc("retry")}
        </Button>
      }
    />
  );
}
