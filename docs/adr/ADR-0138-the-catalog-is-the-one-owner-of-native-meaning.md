---
description: "Decision to make the harness catalog the single semantic owner for every capture path, replacing setup import's private classification table."
last_verified: "2026-09-01"
---

# ADR-0138: The catalog is the one owner of native meaning

Status: accepted.

## Context

The CLI had two independent capture engines for one physical configuration.
`component discover`/`component adopt` classified native paths through
`harness_catalog` — the declarative table that knows each harness's layouts,
declared keys, excluded names and scopes — while `setup import` carried its own
`_component_boundary()`: five directory names, a filename-contains-`mcp`
heuristic, and two instruction filenames.

Measured on 2026-09-01, the private table misread surfaces the catalog two
files away already knew: claude-code `rules/` became a `setting` instead of an
`instruction`, codex `prompts/` a `setting` instead of a `command`, pi
`extensions/` a `setting` instead of a `plugin`, antigravity
`config/global_workflows/` a `setting` instead of a `command`, and every MCP
block declared inside `config.toml`, `opencode.json` or `settings.json#hooks`
dissolved into the surrounding setting. Cursor's `plugins/local/<name>` all
collapsed into one aggregate boundary named `local`. The same tree captured
through the two paths produced two different component graphs.

The import path also read the tree less carefully than adoption: `rglob`
descends symlinked directories, `is_file()` follows file links, hardlinks were
captured, and only JSON was sanitized — a `config.toml` carrying
`env = { TOKEN = "…" }` under an MCP server went into the content store whole.

## Considered options

**Extend `_component_boundary()` with more names.** Rejected: every extension
copies a fact the catalog already owns, and the copy starts drifting the day it
lands — this is the exact two-tables defect `AGENTS.md` forbids for documents,
committed in code.

**Make import call `component discover` per path.** Rejected: discovery answers
"what components exist at the declared layouts", import answers "what is every
file in this tree"; forcing one shape onto the other loses import's total
inventory, which the plan digest and the completeness refusal depend on.

**One resolver, catalog-driven, consumed by both.** Accepted.

## Decision

`setup import` classifies every inspected file through the harness catalog's
global layouts, longest path first. A directory layout claims its first child
as the component boundary — which is what makes `plugins/local/<name>` one
plugin per name. A file layout claims the exact path; one with a
`declared_key` yields a contribution candidate only when the file structurally
declares entries under that key, with the entry names as native identities and
`path#key` as the boundary — the same claim spelling `composition` already
uses. A file no layout claims stays a per-file `setting`: captured, never
guessed into another kind, never dropped.

The registered artifact of a contribution carries the extracted key value —
`contribution.extract_value`, the same route adoption and installation use —
sanitized in the host's own format, never the host file.

Sanitization is structural per format: JSON as before, JSONC through the same
comment stripper discovery trusts, TOML through `tomlkit` so a person's
comments survive the rewrite, YAML through `safe_load`. Every inventory row
records which rewrite actually ran; an unparsed file is reported untouched
rather than implied clean.

Reading is shared discipline (`local/reading.py`): classification by `lstat`
that follows nothing, refusal of symlinks, Windows reparse points, hardlinks
and special files, `O_NOFOLLOW` plus an inode re-check on the registration
read, and a bound on the walk. Refused paths are reported per file, and
registration is complete by default — a capture that left anything out
registers only when the operator says `partial`, and the passport then records
the mode and the exact paths.

## Consequences

Import plans and candidate identities change shape: boundaries, declared keys
and entry names now enter the digests, so plans made before this record do not
confirm after it — which is the digest doing its job.

`state_paths` coverage becomes the next visible gap: the catalog names runtime
state for claude-code and codex only, so the other five harnesses' caches are
still importable as authored configuration. The catalog is now the single
place to fix that.

Adoption keeps its own stricter per-component limits and messages, but reads
through the same shared discipline, so a third capture path added later starts
safe instead of starting over.

## Reconsideration conditions

If a harness ships a surface whose meaning genuinely cannot be expressed as a
layout row — a component whose boundary depends on file content rather than
placement — the resolver gains a typed extension in the catalog, not a second
private table beside it.
