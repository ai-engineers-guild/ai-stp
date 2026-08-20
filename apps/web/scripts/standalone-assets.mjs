/**
 * Mirror the production image layout into `.next/standalone`.
 *
 * `next build` with `output: "standalone"` emits `server.js` and the server
 * chunks, but not the static assets: `Dockerfile.prod` copies `public/` and
 * `.next/static` in as separate steps. Without the same copy locally the
 * standalone server cannot be started outside Docker, and the Playwright
 * regression suite has to fall back to `next start` — which serves a different
 * artifact from the one production runs (ADR-0040, REQ-2403).
 */
import { cpSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = process.env.AI_STP_NEXT_DIST_DIR ?? ".next";
const standalone = path.join(root, distDir, "standalone");

if (!existsSync(standalone)) {
  console.error(`standalone-assets: ${distDir}/standalone is missing — run \`next build\` first`);
  process.exit(1);
}

const staticSrc = path.join(root, distDir, "static");
if (!existsSync(staticSrc)) {
  console.error(`standalone-assets: ${distDir}/static is missing — the build did not complete`);
  process.exit(1);
}
cpSync(staticSrc, path.join(standalone, distDir, "static"), { recursive: true });

// public/ is optional: the tree carries only the MSW worker today.
const publicSrc = path.join(root, "public");
if (existsSync(publicSrc)) {
  cpSync(publicSrc, path.join(standalone, "public"), { recursive: true });
}

// Fumadocs local-md resolves Markdown at runtime for optional catch-all routes.
// Keep the repository-owned sources beside the standalone server.
const contentSrc = path.join(root, "content");
if (existsSync(contentSrc)) {
  cpSync(contentSrc, path.join(standalone, "content"), { recursive: true });
}

// Next.js 15 can omit this statically required directory from the Windows
// standalone trace when next.config.ts is loaded by the production server.
// Mirror it explicitly so the local artifact is identical to the Docker one.
const nextBuildOutputSrc = path.join(root, "node_modules", "next", "dist", "build", "output");
if (existsSync(nextBuildOutputSrc)) {
  cpSync(
    nextBuildOutputSrc,
    path.join(standalone, "node_modules", "next", "dist", "build", "output"),
    { recursive: true },
  );
}

console.log(
  `standalone-assets: public, content and ${distDir}/static mirrored into standalone output`,
);
