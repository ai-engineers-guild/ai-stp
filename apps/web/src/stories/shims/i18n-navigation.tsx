import type { ComponentProps, ReactNode } from "react";

type Href = string | { pathname: string; query?: Record<string, string> };

function hrefToString(href: Href): string {
  if (typeof href === "string") {
    return href;
  }
  const params = new URLSearchParams(href.query ?? {});
  const q = params.toString();
  return q ? `${href.pathname}?${q}` : href.pathname;
}

export function Link({
  href,
  children,
  ...props
}: {
  href: Href;
  children?: ReactNode;
  className?: string;
  prefetch?: boolean;
} & Omit<ComponentProps<"a">, "href">) {
  const { prefetch: _prefetch, ...rest } = props;
  return (
    <a href={hrefToString(href)} {...rest}>
      {children}
    </a>
  );
}

export function useRouter() {
  return {
    push: () => undefined,
    replace: () => undefined,
    refresh: () => undefined,
    prefetch: async () => undefined,
  };
}

export function usePathname(): string {
  return "/";
}
