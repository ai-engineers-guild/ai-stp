import { spawn } from "node:child_process";
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const port = process.env.VERIFY_PORT ?? "3193";
const url = process.env.VERIFY_URL ?? `http://127.0.0.1:${port}`;
const serverEntry = process.env.VERIFY_SERVER_ENTRY ?? ".next/standalone/server.js";
// Where run evidence lands. The default sits inside this app, under an
// already-ignored directory, so a verification run never writes into a
// sibling tool's working directory or leaves artifacts git tracks.
const reviewDir = resolve(process.env.VERIFY_REVIEW_DIR ?? "test-results/review");
const lighthouseReport = join(reviewDir, "lighthouse.json");
const standaloneRoot = dirname(resolve(serverEntry));
const buildRoot = dirname(standaloneRoot);

// Next standalone output intentionally excludes public and static assets. Stage
// them beside server.js so verification exercises the same files production serves.
if (existsSync(join(buildRoot, "static"))) {
  cpSync(join(buildRoot, "static"), join(standaloneRoot, basename(buildRoot), "static"), {
    recursive: true,
    force: true,
  });
}
if (existsSync(resolve("public"))) {
  cpSync(resolve("public"), join(standaloneRoot, "public"), { recursive: true, force: true });
}
const server = spawn(process.execPath, [resolve(serverEntry)], {
  cwd: standaloneRoot,
  env: { ...process.env, PORT: port, HOSTNAME: "127.0.0.1" },
  stdio: ["ignore", "pipe", "pipe"],
});

async function waitUntilReady() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (server.exitCode !== null) {
      throw new Error(`Production server exited with ${String(server.exitCode)}`);
    }
    try {
      const response = await fetch(`${url}/en`);
      if (response.ok) return;
    } catch {
      // Server is still starting.
    }
    await delay(500);
  }
  throw new Error(`Production server did not become ready at ${url}`);
}

function run(command, args, env = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      env: { ...process.env, ...env },
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} exited with ${String(code)}`));
    });
  });
}

try {
  mkdirSync(reviewDir, { recursive: true });
  await waitUntilReady();
  if (process.env.VERIFY_SKIP_LIGHTHOUSE !== "1")
    try {
      await run("bunx", [
        "lighthouse@13.4.1",
        `${url}/en`,
        "--quiet",
        "--chrome-path=C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "--chrome-flags=--headless --no-sandbox",
        "--only-categories=performance,accessibility,best-practices,seo",
        "--output=json",
        `--output-path=${lighthouseReport}`,
      ]);
    } catch (error) {
      // Lighthouse on Windows can finish the report and then fail to remove its
      // temporary profile with EPERM. A written report is still valid evidence.
      if (!existsSync(lighthouseReport)) throw error;
    }
  if (process.env.VERIFY_SKIP_E2E !== "1") {
    await run("bun", ["x", "playwright", "test", "tests/e2e/shell-machine-contact.spec.ts"], {
      PLAYWRIGHT_EXTERNAL_BASE_URL: url,
    });
  }
} finally {
  server.kill("SIGTERM");
}
