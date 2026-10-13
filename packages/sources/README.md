# ai-stp-sources

Shared internal `SourceIntent` / `SourceSnapshot` contracts and adapters for
GitHub, bounded local paths and the closed official package registries
(SPEC-057, ADR-0139). Resolution never grants
`author_verified`, `component_verified`, or target-write authority.

The embedded-definition writer derives invocation names from captured native
bytes and mapped paths for the Rust consumer's Markdown and MCP readers.
Harness-specific visibility, aliases, YAML dialects and credential references
remain distinct. Existing immutable definitions are never re-sealed. The shared
native fixture corpus and CLI acquisition regression exercise this boundary.
Pi's captured ignore files use `pathspec`; the source package owns this runtime
dependency, removable with its Pi visibility reader. No harness is executed or
installed while freezing a definition.

Go checksum evidence follows upstream `dirhash.HashZip(Hash1)`: sorted original
file names and per-file content hashes, independent of ZIP encoding. The reader
bounds all module content, rejects ambiguous/escaping entries and compares the
result with the official checksum endpoint. This is an HTTPS observation, not
verification of the checksum database's signed transparency log. The separate
archive digest continues to bind the exact downloaded bytes.
Proxy and checksum lookup URLs case-encode both module and version; snapshot
identities and archive member names retain their original case.

Source and specifications live in the
[ai_stp repository](https://github.com/ai-engineers-guild/ai-stp).
