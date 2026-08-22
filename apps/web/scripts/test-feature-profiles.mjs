import { spawnSync } from "node:child_process";

const scenarios = [
  { profile: "public_saas", content: "true", saas: "true" },
  { profile: "self_hosted", content: "false", saas: "false" },
];

for (const scenario of scenarios) {
  const env = {
    ...process.env,
    AI_STP_WEB_PROFILE: scenario.profile,
    AI_STP_EXPECT_CONTENT_HUB: scenario.content,
    AI_STP_EXPECT_SAAS_PUBLIC_PAGES: scenario.saas,
  };
  run("bun", ["run", "build"], env);
  run(
    "bunx",
    ["playwright", "test", "tests/e2e/feature-profile.spec.ts", "--project=chromium"],
    env,
  );
}

function run(command, args, env) {
  // Windows resolves `bun`/`bunx` through PATHEXT, and what is on PATH may be a
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
