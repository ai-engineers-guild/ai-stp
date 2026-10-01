/** Translate a continuation's argv into (path, values, flags) for the
 *  gated IPC commands. The command path is NOT inferred from argv — the
 *  continuation carries it as `path` — so positional words in argv are a
 *  contract violation and are refused rather than silently dropped. */
export function argvToCall(
  path: string[],
  argv: string[],
): { path: string; values: Record<string, string>; flags: string[] } | null {
  const key = path.join(" ");
  if (!key) return null;
  const words = argv.filter((a) => a !== "--json");
  // The first `path.length` words must be exactly the declared path —
  // otherwise flag positions are misaligned.
  if (path.some((w, i) => words[i] !== w)) return null;
  const rest = words.slice(path.length);
  const values: Record<string, string> = {};
  const flags: string[] = [];
  for (let i = 0; i < rest.length; i++) {
    if (!rest[i].startsWith("--")) return null; // positional at flag position
    const name = rest[i].slice(2);
    if (i + 1 < rest.length && !rest[i + 1].startsWith("--")) {
      values[name] = rest[i + 1];
      i++;
    } else {
      flags.push(name);
    }
  }
  return { path: key, values, flags };
}
