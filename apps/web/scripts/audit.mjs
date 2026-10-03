#!/usr/bin/env node
/**
 * Retry `bun audit` when the advisory endpoint is unavailable.
 * A real finding still fails. A 503 is not a vulnerability.
 */
import { spawnSync } from "node:child_process";

const attempts = 4;
const retry = /503|ECONNRESET|ETIMEDOUT|ENOTFOUND|socket hang up|advisory bulk/i;

// GHSA-vfj7-8cjw-p6xm (braces <=3.0.3 stack exhaustion) has no patched release
// upstream (micromatch/braces#70) and no parent bump can drop it, since
// micromatch@4.0.8 pins braces@^3.0.3. The installed bytes carry the
// upstream-recommended depth guard via patchedDependencies
// (patches/braces@3.0.3.patch); bun audit still reports the registry version
// string. The ignore expires with the osv-scanner.toml exception on
// 2026-11-03: after that this gate fails again until upstream is re-checked.
const ignoreExpiry = Date.UTC(2026, 10, 3);
const ignores = [];
if (Date.now() < ignoreExpiry) {
  ignores.push("--ignore=GHSA-vfj7-8cjw-p6xm");
  process.stdout.write(
    "audit: ignoring GHSA-vfj7-8cjw-p6xm until 2026-11-03 (braces bytes patched via patchedDependencies)\n",
  );
}

for (let attempt = 1; attempt <= attempts; attempt += 1) {
  const result = spawnSync("bun", ["audit", "--audit-level=high", ...ignores], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  process.stdout.write(result.stdout ?? "");
  process.stderr.write(result.stderr ?? "");
  if (result.status === 0) {
    process.exit(0);
  }
  const transient = retry.test(output) || result.error;
  if (!transient || attempt === attempts) {
    process.exit(result.status === null ? 1 : result.status);
  }
  const waitMs = 2000 * attempt;
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, waitMs);
}

process.exit(1);
