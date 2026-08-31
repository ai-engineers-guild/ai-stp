import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

// 3100 collided with another project on the maintainer's machine and the
// failure read as "already used" rather than as a conflict this suite could
// have avoided. 6767 is chosen for being outside the ranges dev servers reach
// for by habit; PLAYWRIGHT_PORT still moves it without editing tracked config.
const port = Number(process.env["PLAYWRIGHT_PORT"] ?? 6767);
const externalBaseURL = process.env["PLAYWRIGHT_EXTERNAL_BASE_URL"];
const baseURL = externalBaseURL ?? `http://127.0.0.1:${String(port)}`;
const nextDistDir = process.env["AI_STP_NEXT_DIST_DIR"] ?? ".next";

export default defineConfig({
  testDir: "./tests/e2e",
  // Mock auth/profile/catalog state is intentionally process-local and shared by
  // routes. Serial execution prevents independent scenarios from mutating the
  // same production server concurrently.
  fullyParallel: false,
  forbidOnly: Boolean(process.env["CI"]),
  retries: process.env["CI"] ? 1 : 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL,
    // Google Chrome as installed, not Playwright's bundled Chromium. What ships
    // to people is Chrome, and the two differ in exactly the places a browser
    // test is worth having — codecs, PDF, DRM and the release cadence itself.
    // A regression that only Chrome shows is one this suite could not see.
    channel: "chrome",
    trace: "on-first-retry",
    storageState: {
      cookies: [
        {
          name: "ai_stp_consent",
          value: "v1.none",
          domain: "127.0.0.1",
          path: "/",
          expires: -1,
          httpOnly: false,
          secure: false,
          sameSite: "Lax",
        },
      ],
      origins: [],
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "chromium-mobile",
      use: { ...devices["Pixel 7"] },
    },
  ],
  ...(externalBaseURL
    ? {}
    : {
        webServer: {
          // The standalone server is the artifact production runs (ADR-0040, REQ-2403).
          // `next start` serves a different one and Next warns about it under
          // `output: "standalone"`; regression must exercise what actually ships.
          command: `node ${nextDistDir}/standalone/server.js`,
          url: baseURL,
          // Always start a dedicated server so a leftover/corrupt process cannot
          // satisfy the gate (standalone/output mixed builds, a stale server).
          reuseExistingServer: false,
          timeout: 120_000,
          env: {
            ...process.env,
            // The standalone server takes its bind address from the environment; there
            // is no --port flag to pass.
            PORT: String(port),
            HOSTNAME: "127.0.0.1",
            // Offline e2e uses in-process mocks (including mock OAuth).
            AI_STP_USE_MOCKS: "true",
            AI_STP_MOCK_AUTH: "true",
            AI_STP_API_BASE_URL: "http://127.0.0.1:8000",
            NEXT_PUBLIC_APP_URL: baseURL,
            AI_STP_SESSION_SECRET: "playwright-session-secret-32chars-min",
            AI_STP_USER_FACING_ROOT: path.resolve(process.cwd(), "..", "..", "docs-user-facing"),
          },
        },
      }),
});
