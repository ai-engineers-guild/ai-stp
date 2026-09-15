/**
 * Mirror the production image layout into `.next/standalone`.
 *
 * `next build` with `output: "standalone"` emits `server.js` and the server
 * chunks, but not the static assets. This script mirrors `public/` and
 * `.next/static` beside the standalone server so local Playwright exercises
 * the same artifact shape as production (ADR-0040, REQ-2403).
 */
import { cpSync, existsSync, readFileSync } from "node:fs";
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

// Read the artifact's baked features, never the invoking shell's runtime profile.
const requiredServerFiles = path.join(root, distDir, "required-server-files.json");
if (!existsSync(requiredServerFiles)) {
  throw new Error(`standalone-assets: ${distDir}/required-server-files.json is missing`);
}
const compiled = JSON.parse(readFileSync(requiredServerFiles, "utf8")).config?.env;
if (
  typeof compiled?.AI_STP_COMPILED_FEATURE_PROFILE !== "string" ||
  !["true", "false"].includes(compiled.AI_STP_COMPILED_FEATURE_CONTENT_HUB) ||
  !["true", "false"].includes(compiled.AI_STP_COMPILED_FEATURE_SAAS_PUBLIC_PAGES)
) {
  throw new Error("standalone-assets: required-server-files.json has invalid baked feature values");
}
const contentEnabled = compiled.AI_STP_COMPILED_FEATURE_CONTENT_HUB === "true";
const legalEnabled = compiled.AI_STP_COMPILED_FEATURE_SAAS_PUBLIC_PAGES === "true";
cpSync(staticSrc, path.join(standalone, distDir, "static"), { recursive: true });

// public/ is optional: profile-gated static assets are copied from the build source.
const publicSrc = path.join(root, "public");
if (existsSync(publicSrc)) {
  cpSync(publicSrc, path.join(standalone, "public"), {
    recursive: true,
    filter: (source) =>
      contentEnabled || path.relative(publicSrc, source).split(path.sep)[0] !== "content",
  });
}

// Fumadocs and the Content Hub resolve Markdown at runtime. Keep the single
// repository-owned enabled source trees beside the standalone server.
const userFacingSrc = process.env.AI_STP_USER_FACING_ROOT
  ? path.resolve(process.env.AI_STP_USER_FACING_ROOT)
  : path.resolve(root, "..", "..", "docs-user-facing");
if (existsSync(userFacingSrc)) {
  for (const tree of [
    "docs",
    ...(contentEnabled ? ["content"] : []),
    ...(legalEnabled ? ["legal"] : []),
  ]) {
    const source = path.join(userFacingSrc, tree);
    if (existsSync(source)) {
      cpSync(source, path.join(standalone, "docs-user-facing", tree), { recursive: true });
    }
  }
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
  `standalone-assets: public, user-facing sources and ${distDir}/static mirrored into standalone output`,
);
