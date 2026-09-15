export function localeNeutralPathname(pathname: string): string {
  return pathname.replace(/^\/(?:en|ru)(?=\/|$)/, "") || "/";
}
