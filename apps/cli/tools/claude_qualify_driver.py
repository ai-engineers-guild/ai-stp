#!/usr/bin/env python3
"""agy-argv -> `claude` adapter for the isolated qualify runner.

`ai_stp_cli.agy_qualify` drives an agent binary through agy-style argv.
Point `--agy` at this executable to qualify with Claude Code instead:

    python -m ai_stp_cli.agy_qualify --root <dir> --scenario <name> --run <n> \
        --agy apps/cli/tools/claude_qualify_driver.py \
        --model claude-haiku-4-5 --measured <overlay.json>

The overlay records `--model` verbatim; name the exact model driven so the
cells are honestly attributed.

Translation:
  --print=<text> / --print <text>   -> -p <text>
  --model <m>                       -> --model <m> (passed through)
  --mode accept-edits               -> --permission-mode acceptEdits
  --dangerously-skip-permissions    -> passthrough
  --add-dir <d>                     -> passthrough
  --output-format json              -> passthrough
  --print-timeout <t>               -> dropped (claude has no such flag)
"""

import os
import sys


def main() -> None:
    args = sys.argv[1:]
    out = ["claude"]
    prompt: str | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--print="):
            prompt = arg[len("--print=") :]
        elif arg == "--print":
            i += 1
            prompt = args[i] if i < len(args) else None
        elif arg == "--mode":
            i += 1
            out += ["--permission-mode", "acceptEdits"]
        elif arg == "--print-timeout":
            i += 1
        elif arg in ("--model", "--output-format", "--add-dir"):
            i += 1
            if i < len(args):
                out += [arg, args[i]]
        else:
            out.append(arg)
        i += 1
    if prompt is not None:
        out += ["-p", prompt]
    os.execvp("claude", out)


if __name__ == "__main__":
    main()
