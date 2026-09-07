# Setup

Create or improve a complete native tool collection for the user's tasks.
Start from the builder's ai-stp lifecycle guidance: define acceptance scenarios,
inventory existing components, select exact versions, fill missing capabilities,
compose the graph, validate it, and deliver invocation and recovery instructions.

Ask `codex-setup-system list` for the shipped presets. Their names describe
payload composition, not different authority levels. Read the selected payload
and its documented policy; do not assume `minimal` means product defaults or
that only a preset named `full-auto` supports autonomous work.

Rules a setup must satisfy, each held by a guard:

- **Write the product's own keys.** A correct key at a correct path that the
  product does not read leaves a target that looks configured and is not.
- **Cite a page for the format.** A setup writing configuration and naming no
  source is refused.
- **Two setups may not carry the same bytes.** A posture that installs what
  another installs is a posture in name only and still reads as offered.
- **A component entry point describes itself.** A `SKILL.md` without a
  `description` gives the model nothing to choose on.
- **No two files may differ only in case.** They are one file on macOS and
  Windows and two on Linux.

Exercise the setup's intended tasks and backup/restore in disposable targets.
If changing provider implementation, also run this tree's checks:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

If a command is not present, say so rather than working around it.
