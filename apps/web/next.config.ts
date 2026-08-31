import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

import { resolveDevApiRewrites } from "./src/lib/dev-api-rewrites";
import { resolveFeatureProfile } from "./src/lib/features/load-profile";
import { assertContentLocaleParity } from "./src/lib/content/source";

const withNextIntl = createNextIntlPlugin("./src/lib/i18n/request.ts");
const featureProfile = resolveFeatureProfile(process.cwd(), process.env);
assertContentLocaleParity();

const isDevelopment = process.env.NODE_ENV === "development";
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://mc.yandex.ru https://mc.yandex.com${isDevelopment ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://avatars.githubusercontent.com https://lh3.googleusercontent.com https://i.ytimg.com https://raw.githubusercontent.com https://www.google-analytics.com https://www.googletagmanager.com https://mc.yandex.ru https://mc.yandex.com",
  "media-src 'self' blob: https://raw.githubusercontent.com",
  "frame-src https://www.youtube-nocookie.com",
  "font-src 'self'",
  "connect-src 'self' https://www.google-analytics.com https://www.googletagmanager.com https://mc.yandex.ru https://mc.yandex.com",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self' mailto:",
  "frame-ancestors 'none'",
  "upgrade-insecure-requests",
].join("; ");

const nextConfig: NextConfig = {
  env: {
    AI_STP_COMPILED_FEATURE_PROFILE: featureProfile.profile,
    AI_STP_COMPILED_FEATURE_CONTENT_HUB: String(featureProfile.features.content_hub),
    AI_STP_COMPILED_FEATURE_SAAS_PUBLIC_PAGES: String(featureProfile.features.saas_public_pages),
    AI_STP_COMPILED_FEATURE_CATALOG_USAGE_METRICS: String(
      featureProfile.features.catalog_usage_metrics,
    ),
  },
  // CI/diagnostics may isolate build artifacts when another local build owns .next.
  ...(process.env["AI_STP_NEXT_DIST_DIR"] ? { distDir: process.env["AI_STP_NEXT_DIST_DIR"] } : {}),
  reactStrictMode: true,
  devIndicators: false,
  poweredByHeader: false,
  compress: true,
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "avatars.githubusercontent.com" },
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
      { protocol: "https", hostname: "raw.githubusercontent.com" },
    ],
  },
  headers() {
    return Promise.resolve([
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), browsing-topics=()",
          },
        ],
      },
      {
        source: "/_next/static/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: isDevelopment ? "no-store" : "public, max-age=31536000, immutable",
          },
        ],
      },
    ]);
  },
  // Lean production image: copy .next/standalone into a minimal Node runtime (REQ-2403).
  output: "standalone",
  // Tree-shake icon/UI packages; client router cache for snappy soft navigations.
  // Next 15 defaults dynamic staleTime to 0 (always re-fetch RSC on every click).
  experimental: {
    optimizePackageImports: ["lucide-react", "@radix-ui/react-slot", "sonner"],
    staleTimes: {
      dynamic: 30,
      static: 180,
    },
  },
  // Dev-only: same-origin /v1 (and API docs) → internal API without a host proxy.
  // Prod keeps the path split in the host's nginx (ADR-0135); rewrites stay empty there.
  rewrites() {
    return Promise.resolve(
      resolveDevApiRewrites(process.env.NODE_ENV, process.env.AI_STP_API_BASE_URL),
    );
  },
  // typedRoutes off for mock-first MVP: returnTo paths are dynamic query strings.
  eslint: {
    // Lint is enforced by `bun run lint` / check-web; avoid double gate during build.
    ignoreDuringBuilds: true,
  },
  typescript: {
    // Typecheck is enforced by TS7 `type-check` script (ADR-0043).
    ignoreBuildErrors: false,
  },
};

export default withNextIntl(nextConfig);
