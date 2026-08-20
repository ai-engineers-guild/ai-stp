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
  void error;
  return (
    <StatePanel
      kind="error"
      title={t("errorTitle")}
      description={t("errorBody")}
      action={
        <Button type="button" onClick={reset}>
          {tc("retry")}
        </Button>
      }
    />
  );
}
