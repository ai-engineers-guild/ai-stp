import { createHash } from "node:crypto";
import {
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createClient } from "@hey-api/openapi-ts";
import { format } from "prettier";

const root = fileURLToPath(new URL("../", import.meta.url));
const directory = path.join(root, "src/generated");
const native = JSON.parse(
  readFileSync(path.join(directory, "native-bindings.json"), "utf8"),
);
for (const [name, digest] of Object.entries(native.inputs)) {
  const source = readFileSync(path.join(root, name), "utf8").replaceAll(
    "\r\n",
    "\n",
  );
  if (createHash("sha256").update(source).digest("hex") !== digest)
    throw new Error(
      `${name}: compiled native projection is stale; run just desktop-native-gen on an execution host`,
    );
}
const nativeTypes = await format(
  `// Generated from the compiled Rust IPC owner; do not edit.\n${native.declarations.map((declaration) => `export ${declaration}`).join("\n")}\n`,
  { parser: "typescript" },
);

const schemas = {};
const documents = [
  "cli-machine-help",
  "cli-task",
  "cli-task-intents",
  "cli-envelope-success",
];
for (const name of documents) {
  const document = JSON.parse(
    readFileSync(
      new URL(`../../../schemas/v1/${name}.schema.json`, import.meta.url),
      "utf8",
    ),
  );
  for (const [key, definition] of Object.entries({
    ...document.$defs,
    [document.title]: Object.fromEntries(
      Object.entries(document).filter(
        ([key]) => key !== "$defs" && key !== "$schema",
      ),
    ),
  })) {
    if (
      schemas[key] &&
      JSON.stringify(schemas[key]) !== JSON.stringify(definition)
    )
      throw new Error(`Conflicting canonical CLI definition: ${key}`);
    schemas[key] = definition;
  }
}
function references(value) {
  if (Array.isArray(value)) return value.map(references);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [
        key,
        key === "$ref"
          ? child.replace("#/$defs/", "#/components/schemas/")
          : references(child),
      ]),
    );
  return value;
}
const temporary = mkdtempSync(path.join(tmpdir(), "desktop-contracts-"));
const output = new Map([["native.ts", nativeTypes]]);
try {
  const input = path.join(temporary, "cli.json");
  writeFileSync(
    input,
    JSON.stringify({
      openapi: "3.1.0",
      info: { title: "ai-stp CLI display contracts", version: "1" },
      paths: {},
      components: { schemas: references(schemas) },
    }),
  );
  const generated = path.join(temporary, "output");
  await createClient({
    input,
    output: { path: generated, postProcess: [] },
    plugins: [{ name: "@hey-api/typescript", enums: false }],
  });
  const files = readdirSync(generated);
  if (!files.includes("types.gen.ts"))
    throw new Error("CLI type generator produced no declarations");
  output.set(
    "cli.ts",
    await format(readFileSync(path.join(generated, "types.gen.ts"), "utf8"), {
      parser: "typescript",
    }),
  );
  output.set(
    "contract-rules.ts",
    await format(
      `// Generated from canonical CLI schemas; do not edit.\nexport const personalOwnershipSchema = ${JSON.stringify(schemas.NativePersonalTaskOwnership)} as const;\nexport const taskStates = ${JSON.stringify(schemas.TaskState.enum)} as const;\nexport const taskIntents = ${JSON.stringify(schemas.TaskIntent.enum)} as const;\nexport const taskActors = ${JSON.stringify(schemas.TaskActor.enum)} as const;\n`,
      { parser: "typescript" },
    ),
  );
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
for (const [name, expected] of output) {
  const target = path.join(directory, name);
  if (process.argv.includes("--check")) {
    if (readFileSync(target, "utf8") !== expected)
      throw new Error(
        `Desktop contract projection is stale: ${name}; run just desktop-gen`,
      );
  } else writeFileSync(target, expected);
}
