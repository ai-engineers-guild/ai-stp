import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { format } from "prettier";

const tokens = JSON.parse(
  readFileSync(
    new URL("../../web/src/theme/tokens.json", import.meta.url),
    "utf8",
  ),
);
const desktop = tokens.platform.desktop;
const lines = [
  "/* Generated from apps/web/src/theme/tokens.json; do not edit. */",
];
for (const [selector, mode] of [
  [":root", "light"],
  [".dark", "dark"],
]) {
  lines.push(`${selector} {`);
  for (const [name, modes] of Object.entries(tokens.color))
    lines.push(
      `  --${name}: ${(desktop.color[name]?.[mode] ?? modes[mode]).$value};`,
    );
  if (mode === "light")
    for (const [name, token] of Object.entries(tokens.icon.size))
      lines.push(`  --icon-${name}: ${token.$value};`);
  lines.push("}");
}
lines.push("@theme inline {");
for (const name of Object.keys(tokens.color))
  lines.push(`  --color-${name}: hsl(var(--${name}));`);
for (const [name, token] of Object.entries(desktop.font.family))
  lines.push(
    `  --font-${name}: ${token.$value.map((value) => (value.includes(" ") ? JSON.stringify(value) : value)).join(", ")};`,
  );
for (const [name, token] of Object.entries(tokens.radius))
  lines.push(`  --radius-${name}: ${token.$value};`);
for (const [name, token] of Object.entries({
  ...tokens.font.size,
  ...desktop.font.size,
}))
  lines.push(`  --text-${name}: ${token.$value};`);
for (const [name, token] of Object.entries(tokens.font.weight))
  lines.push(`  --font-weight-${name}: ${token.$value};`);
for (const [name, token] of Object.entries(tokens.font.lineHeight))
  lines.push(`  --leading-${name}: ${token.$value};`);
for (const [name, token] of Object.entries(tokens.shadow))
  lines.push(`  --shadow-${name}: ${token.$value};`);
lines.push(`  --spacing: ${tokens.space["1"].$value};`);
lines.push(
  `  --default-transition-duration: ${tokens.motion.duration.fast.$value};`,
);
lines.push("}");
const output = new Map([
  ["theme.css", await format(lines.join("\n"), { parser: "css" })],
  [
    "theme.ts",
    await format(
      `// Generated from product icon tokens; do not edit.\nexport const iconSize = { ${Object.keys(
        tokens.icon.size,
      )
        .map(
          (name) =>
            `${JSON.stringify(name)}: { width: "var(--icon-${name})", height: "var(--icon-${name})" }`,
        )
        .join(",")} } as const;\n`,
      { parser: "typescript" },
    ),
  ],
]);
for (const [name, expected] of output) {
  const target = new URL(`../src/generated/${name}`, import.meta.url);
  if (process.argv.includes("--check")) {
    if (readFileSync(target, "utf8") !== expected)
      throw new Error("Desktop theme is stale; run just desktop-gen");
  } else {
    mkdirSync(new URL("../src/generated/", import.meta.url), {
      recursive: true,
    });
    writeFileSync(target, expected);
  }
}
