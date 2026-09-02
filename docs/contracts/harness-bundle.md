---
description: "Bounded deterministic package for a public harness provider."
last_verified: "2026-09-01"
---

# Harness bundle

## Structure

The `ai-stp-bundle/1` format is a canonical uncompressed ZIP under `ADR-0049`.
It is a byte sequence, not a conceptual directory tree.

```text
bundle.json
setup-passport.json
composition-report.json
conversion-report.json
files/
attestations/
```

The `setup-passport.json` file is a setup-version passport under `component-setup-passports.md`. The `attestations/` directory is required: the separation of evidence sources under `ADR-0007` depends on it.

`SetupVersionPassport.artifact` refers to the independent canonical version
definition under `ADR-0051`, not to this ZIP. The passport can therefore be
included in the ZIP without a self-reference; `artifact.digest`, `bundle_digest`,
and raw-ZIP `artifact_digest` remain three distinct identities with distinct checks.

Member order matches the order above; managed files follow `files/` in manifest
order, and `attestations/` comes last. Every member timestamp is fixed at
`1980-01-01T00:00:00`, the creator is Unix, extra/comment are empty, and no
compression is used. JSON members are canonical RFC 8785 UTF-8 bytes without a
trailing newline. Local time, uid/gid, umask, and filesystem traversal order are
not included in the bundle.

## Bundle manifest

`bundle.json` contains `bundle_format`, schema and protocol versions, an exact
reference to `SetupVersion`, `harness_id`, the setup-compiler version, input hash,
the managed-path set, file manifest, metadata for the three required documents,
common limits, and `bundle_digest`.

`target_scope` names the projection scope the bundle was compiled for and is
present only when it is not `global`: a bundle compiled for the harness
configuration home is byte-identical to one compiled before scopes were chosen,
so every digest a released plan already binds stays what it was. A `project`
bundle's paths are relative to a workspace root, and the plan that installs it
hands the provider that root as its target and the scope as `--target-scope`.

A file record contains a normalized relative path, SHA-256, size, permitted mode, and surface owner. The contents of `files/` must match the manifest exactly.

## Determinism

The same canonical input produces the same record order, identical ZIP bytes,
and two identical hashes. `bundle_digest` is computed in the
`ai-stp:bundle:v1` domain from canonical `bundle.json` **without** the
`bundle_digest` field, then written into that file. `artifact_digest` is the
ordinary SHA-256 of the finished ZIP bytes and is passed alongside the bundle.
A self-reference is neither computed nor guessed. Build time, local path, and
model explanation are not included in the contents.

## Validation before planning

Before any mutation, the provider validates:

- the protocol version and selected harness;
- the bundle hash and every file hash;
- SHA-256 of the exact ZIP bytes before parsing;
- required members, their uniqueness, order, and fixed ZIP metadata;
- environment and platform constraints;
- permitted managed surfaces;
- file count, total size, and individual size;
- absence of unknown required fields;
- completeness of the conversion report;
- correspondence of component kind, native surface, and projection kind to the exact profile;
- nonempty native content for every exact component;
- product grammar of managed JSON/TOML and required full-tree markers;
- authorization, if passed as a confirmed reference.

## Prohibitions

Absolute and parent paths, empty segments, target escapes, symbolic links and directories in place of files, special devices, duplicate normalized paths, case conflicts, undeclared paths, hash mismatches, modes outside the allowed set, and secrets are rejected.

The setup compiler does not and cannot reject hard links: the bundle is assembled from content addressed by hash, not by traversing a directory, so the input has neither an inode nor a link count. They are rejected by whoever reads the filesystem: the component-discovery side and the provider during extraction under `provider-protocol.md`.

An arbitrary executable script is not a separate rejection and does not need to be: its path must be within the composition's declared managed surfaces or it is `path_undeclared`, and its mode must be one of the permitted modes or it is `mode_not_allowed`. The executable bit itself is allowed: native surfaces of some harnesses consist of executable files, and prohibiting them would prohibit a valid composition.

The rejection set is closed. Each rejection has a stable code that does not change with the message text:

| Code | Condition |
|---|---|
| `path_not_relative` | path is absolute, begins with `~`, or contains a drive letter |
| `path_escapes_target` | path contains a `..` segment |
| `path_not_portable` | a segment names a reserved Windows device (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `COM¹`, `COM²`, `COM³`, `LPT1`–`LPT9`, `LPT¹`, `LPT²`, `LPT³` — with any extension, because `NUL.tar.gz` is equivalent to `NUL`), ends with a dot or space, or contains `:` or any of `<`, `>`, `"`, `\|`, `?`, `*`. Source: `learn.microsoft.com/windows/win32/fileio/naming-a-file` |
| `path_empty_segment` | path is empty or contains an empty segment or `.` |
| `path_invalid_character` | path contains NUL or another control character |
| `path_too_long` | UTF-8 path exceeds 1024 bytes or a segment exceeds 255 bytes |
| `path_duplicate` | two files normalize to the same path |
| `path_case_conflict` | two paths differ only in case |
| `path_undeclared` | path is not among the composition's managed paths |
| `declared_path_absent` | the composition declares a managed path and no source provides it |
| `link_not_allowed` | symbolic or hard link, or a directory in place of a file |
| `special_file_not_allowed` | device, socket, or pipe |
| `mode_not_allowed` | file mode is outside the allowed set |
| `secret_in_bundle` | file name indicates stored credentials |
| `file_too_large` | file exceeds the resource limit |
| `bundle_too_large` | bundle exceeds the resource limit |
| `too_many_files` | file count exceeds the resource limit |
| `setup_passport_mismatch` | SetupVersion passport does not match the exact reference by stable ID or digest |

`path_too_long` limits the relative path and segment but **does not** check the
Windows 260-character limit; this is a decision, not an omission. `MAX_PATH`
counts the entire path, while the bundle does not know the root to which it will
be applied: `~/.codex` and `Library/Application Support` under a long user name
differ by more than a hundred characters, so any number here would be a guess
about someone else's home directory. The provider cannot resolve this either:
`validate-bundle` runs before the target is named.

Both ends belong to this side, and the arithmetic becomes exact at the planning
stage: `install plan` rejects before calling `plan-operation` when the length of
`target` plus the longest managed path exceeds the limit on a machine where long
paths are not enabled (`local/windows_paths.py`). No new manifest field is added
for this: `managed_paths` are already listed, and a number stored beside them
would be a second copy of the same fact.

`path_undeclared` and `declared_path_absent` are two sides of one check, and the
latter was added after the former. The rejection "a file arrived but was not
declared" says nothing about completeness: a declared path for which no source
arrived creates no record, so no loop iteration sees it. This was measured on
Windows against antigravity: the passport declared `config/hooks.json` and
`config/hooks/h01.py`, the plan reported "write the 1 declared files," the
provider reported a verified installation, and the installed hook could not
run. The provider was correct: it wrote everything carried by the bundle. The
bundle had been silently weakened.

A declared path is also a root here, as in `composition-reports.md`:
`skills/foo` covers `skills/foo/SKILL.md` and is not `path_undeclared`. A root
under which no file arrived remains `declared_path_absent`.

A path is not silently repaired. Normalization that resolves a collision by
choosing a winner is precisely the automatic conflict resolution that `REQ-626`
prohibits the setup compiler from performing.

A link is rejected based on its kind, not its destination: its destination can
change between reading and installation.

A secret is recognized by name. Opening a file to decide whether it is a secret
is the very action the rule exists to prevent.

A component directory is preserved in full as a deterministic content-addressed
artifact and expanded into the bundle without truncation: nested resources and
executable helper files are included with exact hashes and modes. The top-level
manifest alone is not the component's complete content. Discovery and the
provider independently reject links, special files, exceeded limits, and a
missing required native marker.

## Modes and limits

```text
allowed modes: 0644 and 0755
maximum files: 2000
maximum file size: 4 MiB
maximum finished ZIP bundle size: 64 MiB
```

A mode outside the set is a permissions decision the bundle is not authorized
to make. Limits are declared and returned in the manifest, so a bundle that hits
them is distinguishable from a complete one; such a bundle is rejected, not
truncated.

## No partial bundle

A bundle is either assembled in full or not assembled. A manifest beside a list
of rejections would read as "almost assembled," while a bundle containing an
unaccepted file must not be installed.

## Evidence

The contents of `attestations/` are treated as untrusted input and validated under a separate policy. A signature does not replace bundle validation and does not grant write authorization.

## Lifecycle

Bundle validation creates no state. The exact argv/response contract belongs to
`provider-protocol.md`: validation and the provider plan repeat both identities
and the size of these same ZIP bytes. The immutable operation plan binds the
provider plan to the bundle under `ADR-0050`. Apply revalidates cached bytes and
requires the exact provider plan digest, a lock, a backup, and target revalidation.
