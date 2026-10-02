/** Translate a continuation's argv into (path, values, flags, repeated)
 *  for the gated IPC commands. The command path is NOT inferred from argv
 *  — the continuation carries it as `path` — so positional words in argv
 *  are a contract violation and are refused rather than silently dropped.
 *
 *  Two wire forms are accepted: `--name value` and `--name=value` (the
 *  CLI emits the `=` form for values that start with `-`). A repeated
 *  `--name` collects into `repeated` — collapsing to last-wins would
 *  silently narrow a multi-value plan/apply. */
export function argvToCall(
  path: string[],
  argv: string[],
): {
  path: string;
  values: Record<string, string>;
  flags: string[];
  repeated: Record<string, string[]>;
} | null {
  const key = path.join(" ");
  if (!key) return null;
  const words = argv.filter((a) => a !== "--json");
  // The first `path.length` words must be exactly the declared path —
  // otherwise flag positions are misaligned.
  if (path.some((w, i) => words[i] !== w)) return null;
  const rest = words.slice(path.length);
  const values: Record<string, string> = {};
  const flags: string[] = [];
  const repeated: Record<string, string[]> = {};
  const pushValue = (name: string, v: string) => {
    if (name in repeated) {
      repeated[name].push(v);
    } else if (name in values) {
      repeated[name] = [values[name], v];
      delete values[name];
    } else {
      values[name] = v;
    }
  };
  for (let i = 0; i < rest.length; i++) {
    if (!rest[i].startsWith("--")) return null; // positional at flag position
    const token = rest[i].slice(2);
    const eq = token.indexOf("=");
    if (eq >= 0) {
      pushValue(token.slice(0, eq), token.slice(eq + 1));
      continue;
    }
    if (i + 1 < rest.length && !rest[i + 1].startsWith("--")) {
      pushValue(token, rest[i + 1]);
      i++;
    } else {
      flags.push(token);
    }
  }
  return { path: key, values, flags, repeated };
}
