# Setup

Add or revise a setup in this system.

Every harness offers the same three postures, and the names are the estate's
rather than each product's so that learning them once is enough:

- `baseline` — a working floor
- `minimal` — the product's own defaults
- `full-auto` — nothing asked, nothing sandboxed

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

Say which of these the change touches, then run this tree's checks:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

If a command is not present, say so rather than working around it.
