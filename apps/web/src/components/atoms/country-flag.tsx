import { CATALOG_UNSPECIFIED_FILTER } from "@/lib/catalog-query";
import { cn } from "@/lib/cn";
import { Icon } from "@/theme";

/** Current CIS member states (ISO 3166-1 alpha-2). */
export const CIS_COUNTRY_CODES = ["AM", "AZ", "BY", "KZ", "KG", "MD", "RU", "TJ", "UZ"] as const;

export type CisCountryCode = (typeof CIS_COUNTRY_CODES)[number];

const FLAG_ASSETS: Record<CisCountryCode, string> = {
  AM: "/flags/am.svg",
  AZ: "/flags/az.svg",
  BY: "/flags/by.svg",
  KZ: "/flags/kz.svg",
  KG: "/flags/kg.svg",
  MD: "/flags/md.svg",
  RU: "/flags/ru.svg",
  TJ: "/flags/tj.svg",
  UZ: "/flags/uz.svg",
};

const CIS_SET = new Set<string>(CIS_COUNTRY_CODES);

export function isCisCountryCode(code: string): code is CisCountryCode {
  return CIS_SET.has(code);
}

export function flagAssetFor(code: string): string | undefined {
  const normalized = code.trim().toUpperCase();
  return isCisCountryCode(normalized) ? FLAG_ASSETS[normalized] : undefined;
}

export function CountryFlag({
  code,
  compact = false,
  className,
}: {
  code: string;
  compact?: boolean;
  className?: string;
}) {
  const frame = cn(
    "border-border bg-muted relative flex shrink-0 items-center justify-center overflow-hidden rounded-sm border",
    compact ? "h-4 w-6" : "h-8 w-12",
    className,
  );

  if (code === CATALOG_UNSPECIFIED_FILTER) {
    return (
      <span className={cn(frame, "text-muted-foreground")} data-flag={code}>
        <Icon name="flag" size="sm" />
      </span>
    );
  }

  const normalized = code.trim().toUpperCase();
  const asset = flagAssetFor(normalized);
  if (asset) {
    return (
      <span className={frame} data-flag={code}>
        <img
          src={asset}
          alt=""
          width={compact ? 24 : 48}
          height={compact ? 16 : 32}
          className="h-full w-full object-cover"
          decoding="async"
          draggable={false}
        />
      </span>
    );
  }

  return (
    <span className={frame} data-flag={code}>
      <span className="text-muted-foreground font-mono text-[9px] font-medium tracking-wide">
        {/^[A-Z]{2}$/.test(normalized) ? normalized : "—"}
      </span>
    </span>
  );
}
