# Validate

Run everything that must pass before handing off, in order, and report what each
one said rather than that it passed.

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

If a command here is not present, say so rather than working around it.

Then a lifecycle smoke against a disposable target, never a live home:

```bash
target="$(mktemp -d)/claude-target"
mkdir -p "$target"
claude-setup-system install baseline    --target "$target"
claude-setup-system status              --target "$target"
claude-setup-system select full-auto    --target "$target"
claude-setup-system diff                --target "$target"
claude-setup-system backups             --target "$target"
claude-setup-system restore             --target "$target"
claude-setup-system remove              --target "$target"
```

Then, where a change touched the wire surface or the harness facts, run the
consumer's conformance against the built binary. Ask
`claude-setup-system provider-info` for `harness_id`; that is the value
`--harness` takes. Report the verdict **with the consumer version that gave
it** — the same command answers differently on a released CLI and on a
development one, and a verdict without its version is not a verdict.
