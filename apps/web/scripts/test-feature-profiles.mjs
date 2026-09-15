import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const scenarios = [
  { profile: "public_saas", content: "true", saas: "true" },
  { profile: "self_hosted", content: "false", saas: "false" },
  { profile: "corporate_hub", content: "false", saas: "false" },
];

for (const scenario of scenarios) {
  const env = {
    ...process.env,
    AI_STP_WEB_PROFILE: scenario.profile,
    AI_STP_EXPECT_CONTENT_HUB: scenario.content,
    AI_STP_EXPECT_SAAS_PUBLIC_PAGES: scenario.saas,
  };
  run("bun", ["run", "build"], env);
  const distDir = env.AI_STP_NEXT_DIST_DIR ?? ".next";
  const baked = JSON.parse(readFileSync(path.join(distDir, "required-server-files.json"), "utf8"))
    .config.env;
  assert.equal(baked.AI_STP_COMPILED_FEATURE_PROFILE, scenario.profile);
  assert.equal(baked.AI_STP_COMPILED_FEATURE_CONTENT_HUB, scenario.content);
  assert.equal(baked.AI_STP_COMPILED_FEATURE_SAAS_PUBLIC_PAGES, scenario.saas);
  const manifest = JSON.parse(
    readFileSync(path.join(distDir, "app-path-routes-manifest.json"), "utf8"),
  );
  const routes = Object.keys(manifest);
  assert.ok(routes.length > 0, `${scenario.profile}: route manifest must not be empty`);
  const standalone = path.join(distDir, "standalone");
  for (const [directory, enabled] of [
    ["docs-user-facing/docs", true],
    ["docs-user-facing/content", scenario.content === "true"],
    ["docs-user-facing/legal", scenario.saas === "true"],
    ["public/content", scenario.content === "true"],
  ]) {
    assert.equal(
      existsSync(path.join(standalone, directory)),
      enabled,
      `${scenario.profile}: ${directory} packaging`,
    );
  }
  for (const [tree, enabled] of [
    ["content", scenario.content === "true"],
    ["feed.xml", scenario.content === "true"],
    ["contact", scenario.saas === "true"],
    ["legal", scenario.saas === "true"],
    ["services", scenario.profile !== "corporate_hub"],
    ["countries", scenario.profile !== "corporate_hub"],
  ]) {
    assert.equal(
      routes.some((route) => route.split("/").includes(tree)),
      enabled,
      `${scenario.profile}: compiled ${tree} route modules must ${enabled ? "exist" : "be absent"}`,
    );
  }
  // `bun x`, not `bunx`: CI installs bun from its release archive, which ships
  // the one binary and no `bunx` alongside it.
  run(
    "bun",
    ["x", "playwright", "test", "tests/e2e/feature-profile.spec.ts", "--project=chromium"],
    env,
  );
}

function run(command, args, env) {
  // Windows resolves `bun` through PATHEXT, and what is on PATH may be a
  // `.cmd` shim rather than a `.exe`. Appending `.exe` guessed at one shape and
  // spawn failed to find anything, so this exited 1 in a fraction of a second
  // with nothing on stdout — the job said only that the script failed.
  const windows = process.platform === "win32";
  const result = spawnSync(command, args, { env, stdio: "inherit", shell: windows });
  if (result.error) {
    console.error(`${command} ${args.join(" ")} could not start: ${result.error.message}`);
    process.exit(1);
  }
  if (result.status !== 0) {
    console.error(`${command} ${args.join(" ")} exited with ${result.status ?? "a signal"}`);
    process.exit(result.status ?? 1);
  }
}
