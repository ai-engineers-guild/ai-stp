/**
 * Drift check for the generated contract client.
 *
 * `api:generate` + prettier is the producer; this regenerates into a temporary
 * directory, formats it with the repository configuration, and compares the
 * closed file set byte for byte. Any difference — changed content, a missing
 * file, an extra file — means the committed client drifted from the contract.
 */
import { spawnSync } from "node:child_process";
import { mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const committed = path.join(webRoot, "src", "lib", "api", "generated");
// The runtime-config import is emitted relative to the output directory, so
// the scratch copy must sit beside `generated/` for its `../hey-api.ts` to be
// byte-identical — a temp directory outside the tree proves nothing.
const out = mkdtempSync(path.join(path.dirname(committed), ".api-check-"));

function run(args) {
  const result = spawnSync(process.execPath, args, {
    cwd: webRoot,
    stdio: "inherit",
    env: { ...process.env, AI_STP_WEB_API_OUT: out },
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function tree(root) {
  const found = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else found.push(path.relative(root, full));
    }
  };
  walk(root);
  return found.sort();
}

try {
  run([path.join(webRoot, "node_modules", "@hey-api", "openapi-ts", "bin", "run.js")]);
  run([
    path.join(webRoot, "node_modules", "prettier", "bin", "prettier.cjs"),
    "--config",
    path.join(webRoot, "prettier.config.mjs"),
    "--write",
    `${out}/**/*.ts`,
  ]);

  const expected = new Set(tree(committed));
  const rendered = new Set(tree(out));
  const problems = [];
  for (const name of new Set([...expected, ...rendered])) {
    if (!expected.has(name)) {
      problems.push(`generated file not committed: ${name}`);
    } else if (!rendered.has(name)) {
      problems.push(`committed file no longer generated: ${name}`);
    } else if (
      !readFileSync(path.join(committed, name)).equals(readFileSync(path.join(out, name)))
    ) {
      problems.push(`generated client drifted: ${name}`);
    }
  }
  for (const problem of problems) {
    console.error(problem);
  }
  process.exitCode = problems.length ? 1 : 0;
} finally {
  rmSync(out, { recursive: true, force: true });
}
