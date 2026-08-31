function match(userAgent: string, pattern: RegExp): string | null {
  return userAgent.match(pattern)?.[1]?.replaceAll("_", ".") ?? null;
}

export function browserDeviceLabel(userAgent: string | null): string | null {
  if (!userAgent) return null;

  const edge = match(userAgent, /Edg\/([\d.]+)/);
  const opera = match(userAgent, /OPR\/([\d.]+)/);
  const chrome = match(userAgent, /Chrome\/([\d.]+)/);
  const firefox = match(userAgent, /Firefox\/([\d.]+)/);
  const safari = match(userAgent, /Version\/([\d.]+).*Safari\//);
  const browser = edge
    ? `Edge ${edge}`
    : opera
      ? `Opera ${opera}`
      : chrome
        ? `Chrome ${chrome}`
        : firefox
          ? `Firefox ${firefox}`
          : safari
            ? `Safari ${safari}`
            : null;
  const os = /iPhone/.test(userAgent)
    ? "iPhone"
    : /iPad/.test(userAgent)
      ? "iPad"
      : match(userAgent, /Android [^;)]*; ([^;)]+?)(?: Build[/;]|[;)])/) ||
        (/Android/.test(userAgent) ? "Android" : null) ||
        (/Windows NT/.test(userAgent) ? "Windows" : null) ||
        (/Macintosh/.test(userAgent) ? "macOS" : null) ||
        (/Linux/.test(userAgent) ? "Linux" : null);

  return [browser, os].filter(Boolean).join(" · ") || null;
}
