# Validate

Run everything that must pass before handing off, in order, and report what each
one said rather than that it passed.

```bash
scripts/gate.sh                          # toolchain, fmt, clippy, tests
scripts/check_render.sh --deterministic  # the renderer agrees with itself
scripts/check_render.sh                  # the published trees match this source
```

The last one clones the seven from their remotes and answers a question no local
checkout can. It is the check that catches published trees drifting behind their
own releases.

Then, where a change touched the wire surface or the harness facts, run the
consumer's conformance against the built binary and report the verdict **with
the consumer version that gave it** — the same command answers differently on a
released CLI and on a development one, and a verdict without its version is not
a verdict.
