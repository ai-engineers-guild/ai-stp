/** Storybook shim for next/navigation (no App Router). */

export function useRouter() {
  return {
    push: () => undefined,
    replace: () => undefined,
    refresh: () => undefined,
    prefetch: async () => undefined,
    back: () => undefined,
    forward: () => undefined,
  };
}

export function usePathname(): string {
  return "/en";
}

export function useSearchParams(): URLSearchParams {
  return new URLSearchParams();
}

export function useParams(): Record<string, string> {
  return { locale: "en" };
}

export function useSelectedLayoutSegment(): string | null {
  return null;
}

export function useSelectedLayoutSegments(): string[] {
  return [];
}

export function redirect(_url: string): never {
  throw new Error("redirect is not available in Storybook");
}

export function permanentRedirect(_url: string): never {
  throw new Error("permanentRedirect is not available in Storybook");
}

export function notFound(): never {
  throw new Error("notFound is not available in Storybook");
}

export function forbidden(): never {
  throw new Error("forbidden is not available in Storybook");
}

export function unauthorized(): never {
  throw new Error("unauthorized is not available in Storybook");
}

export function unstable_rethrow(error: unknown): never {
  throw error;
}
