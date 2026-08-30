# Validate

Run everything that must pass before handing off, in order, and report what each
one said rather than that it passed.

**Check which repository you are in first**, because half of these exist in only
one of them. `scripts/gate.sh` and `tools/` belong to the private authoring
monorepo; a checkout of a published `<harness>-setup-system` has neither.

In the authoring repository:

```bash
scripts/state.sh                         # what is true right now, each fact with its command
scripts/gate.sh --render                 # toolchain, fmt, clippy, tests, and the render
scripts/check_render.sh                  # the published trees match this source
```

In a published tree, where those do not exist:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

`check_render.sh` clones the seven from their remotes and answers a question no
local checkout can. It is the check that catches published trees drifting behind
their own releases -- and it runs on `main` and hourly, not on a branch, because
a branch has published nothing yet.

**If a command here is not present, say so rather than working around it.** The
reader of this file is a model, and a missing script is a fact about which
repository it is in, not an obstacle to route past.

Then, where a change touched the wire surface or the harness facts, run the
consumer's conformance against the built binary and report the verdict **with
the consumer version that gave it** — the same command answers differently on a
released CLI and on a development one, and a verdict without its version is not
a verdict.
