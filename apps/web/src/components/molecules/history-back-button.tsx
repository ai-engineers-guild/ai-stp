"use client";

import { Button } from "@/components/atoms/button";
import { useRouter } from "@/lib/i18n/navigation";
import { canGoBack, currentNavigationHref, getNavigationStorage } from "@/lib/navigation-history";
import { UI } from "@/lib/ui-selectors";
import { Icon } from "@/theme";

export function HistoryBackButton({ label, fallback }: { label: string; fallback: string }) {
  const router = useRouter();

  return (
    <Button
      type="button"
      variant="ghost"
      size="default"
      data-ui={UI.navigation.back}
      aria-label={label}
      className="min-h-11 px-2 sm:px-3"
      onClick={() => {
        const storage = getNavigationStorage();
        if (canGoBack(storage, currentNavigationHref(window.location))) router.back();
        else router.push(fallback);
      }}
    >
      <Icon name="arrowLeft" size="sm" />
      {label}
    </Button>
  );
}
