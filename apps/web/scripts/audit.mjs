#!/usr/bin/env node
/**
 * Retry `bun audit` when the advisory endpoint is unavailable.
 * A real finding still fails. A 503 is not a vulnerability.
 */
import { spawnSync } from "node:child_process";

const attempts = 4;
const retry = /503|ECONNRESET|ETIMEDOUT|ENOTFOUND|socket hang up|advisory bulk/i;

for (let attempt = 1; attempt <= attempts; attempt += 1) {
  const result = spawnSync("bun", ["audit", "--audit-level=high"], {
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
