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
  const executable = process.platform === "win32" ? `${command}.exe` : command;
  const result = spawnSync(executable, args, { env, stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
