/**
 * Run a child process with `typescript` resolving to the side-installed TS 6.
 * Used by openapi-ts and (indirectly) tooling that needs a programmatic TS API
 * until TypeScript 7.1 ships a stable one (ADR-0043).
 */
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Module from "node:module";

const require = createRequire(import.meta.url);
const ts6Pkg = path.dirname(require.resolve("typescript6/package.json"));
const ts6Entry = require.resolve("typescript6");

const originalResolveFilename = Module._resolveFilename;
Module._resolveFilename = function (request, parent, isMain, options) {
  if (request === "typescript") {
    return ts6Entry;
  }
  return originalResolveFilename.call(this, request, parent, isMain, options);
};

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error("usage: with-ts6.mjs <command> [args...]");
  process.exit(2);
}

const [command, ...commandArgs] = args;
const result = spawnSync(command, commandArgs, {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: {
    ...process.env,
    NODE_PATH: [ts6Pkg, process.env.NODE_PATH].filter(Boolean).join(path.delimiter),
  },
});
process.exit(result.status ?? 1);
