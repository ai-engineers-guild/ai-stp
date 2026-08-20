const COMPACT_FROM = 10_000;

export function formatUsageCount(value: number, locale: string): string {
  const tag = locale.startsWith("ru") ? "ru" : "en";
  return new Intl.NumberFormat(tag, {
    notation: value >= COMPACT_FROM ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}
