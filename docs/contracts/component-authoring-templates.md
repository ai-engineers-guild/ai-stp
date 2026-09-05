---
description: "Versioned scaffold plans and safe projection of component authoring templates."
last_verified: "2026-09-05"
---

# Component authoring templates

The portable syntax belongs to `SPEC-005` REQ-528, while the complete scaffold lifecycle
belongs to [`SPEC-041`](../../specs/active/SPEC-041-component-scaffold-framework.md). Neither
path publishes an object or writes the final harness state.

## Commands

`component scaffold plan` accepts a type, language, harness variant, name, and new
directory. It writes nothing and returns the template/generator versions, complete
file list, sizes, modes, each file's digest, and the entire plan's digest.
A file is hashed in the `ai-stp:artifact:v1` domain; canonical JSON of the plan inputs
is hashed in the `ai-stp:scaffold-plan:v1` domain; `plan_id` is derived from the first
24 hex characters of the plan digest.

`component scaffold apply` accepts the same inputs and the exact
`--expected-plan-digest`. The CLI rebuilds the plan, reserves a new
directory without overwriting, and creates files with mode `0600`, rolling back its
own incomplete result on failure. An existing target—even an empty one—a symlink,
and a missing parent are rejected; there is no hidden overwrite or merge. The
plan digest is the confirmation (`ADR-0118`); there is no `--confirm` flag.

Declarative `instruction`, `skill`, `command`, `agent`, and `setting` use
`--language none`. Executable `mcp` and `plugin` select `python`, `typescript`,
`javascript`, `rust`, `go`, or `dart-flutter`; `hook` does not accept Rust or Go
because the provider does not perform a hidden source build. The variant is `portable`
or one of the harnesses in the closed registry. If the selected harness has no
independent native form for the type, the plan fails closed before any write.

New writes record `standard_family` as `ai-stp-standard/1` on the descriptor
(`SPEC-060`). Historical descriptors without that field remain validatable and
are not assigned the family on read.

`component adaptation add` renders a second concrete harness projection under
`projections/<harness>/` without changing the original `harness_variant`.
Release freezes every `adaptation_contents` source into the version passport
(`ADR-0143`); a singular `harness_id` draft still produces one adaptation.

The current `component-scaffold/6` directory contains `.ai-stp-template.json`,
`.gitignore`, `component-passport.json`, `eval-profile.json`, README, and editable
source under `source/`. A concrete harness also receives a generated native layout
under `projections/<harness>/`; a portable scaffold has no projection directory.
The current `setup-scaffold/5` wrapper embeds that `/6` component tree for one
concrete harness; `/1`–`/4` remain validatable historical descriptors.
An `instruction` canon is `source/AGENTS.md`; Claude Code projections use
`CLAUDE.md`. The `/3`, `/4`, and `/5` descriptors remain accepted as historical
data, but their old wrapper bytes are never emitted under the `/6` identity.
The passport is a local patch: it contains
no invented source, secrets, tags, or permission to redistribute. The author continues via
`component passport validate`, local registration, and publication plan commands.

For a hook, canonical `source/hook-source.json` stores the event, order, blocking failure
policy, and handler command; the strict schema prohibits extra fields. A concrete
harness derives `hooks.json` and an adjacent executable handler under
`projections/<harness>/`. A portable scaffold writes those derived bytes under
`source/` so discover and adopt of `source/` see a closed-set manifest.
Manifest-directory plugins receive a product manifest. OpenCode and Pi receive a
single JS/TS module without an invented manifest. Marketplace registration is not a
plugin package: it is a separate `setting` that owns an entire native settings file.
Unsupported type/harness combinations are rejected instead of being converted into
another type.

## Author path

1. Run `component scaffold plan`, review the descriptor, every file, and digest,
   then pass unchanged inputs to `component scaffold apply` with the exact plan
   digest.
   Apply initializes one Git root only when the destination is not already inside a
   worktree; Git metadata is outside the deterministic plan and is reported separately.
2. Implement the behavior in `source/` and fill in only confirmed patch facts. For `required_env`,
   record names and purposes, but not values. Add source only after pinning a public
   GitHub commit.
3. Inventory the authoring tree with `component inventory --root` before copying
   anything into a native layout. Generated `projections/` are not independent
   sources. Then run `component discover --root` and `component adopt`, and apply
   the patch through
   `component passport update --expected-revision ... --from ... --confirm`.
4. Run `component passport validate` and the evaluation lifecycle. The saved profile
   shows in advance that core will perform local-static checks, while model/human
   checks without the corresponding runner will honestly remain `not_run`.
5. Record and release an exact version, then use `publication plan` and
   `publication confirm`. The publication checklist is not authorization: source,
   license, evidence, and server-side validation remain mandatory separate boundaries.
   `component version release` and `setup compose` refuse any remaining
   `TODO(ai-stp-scaffold):` marker: a draft is not a canonical adaptation.
6. A `setup scaffold` writes `setup.json` members at
   `components/<name>/projections/<harness>` with `managed_paths` taken from that
   generated native layout. Compose freezes those files into a content-addressed
   `ComponentAdaptation` bound to the exact provider surface. Empty tags and
   draft descriptions fail before any setup version is recorded.

`component template render` reads one regular file of no more than 64 KiB without
following a symlink and returns a validated projection in machine output. The source
file and target remain unchanged. The response contains SHA-256 values of the source
and resulting UTF-8 text so a repeat can be compared byte for byte.

## Closed syntax

Outside fenced code, only four placeholders are allowed:

```text
{{harness_id}}
{{component_name}}
{{component_root}}
{{config_root}}
```

They mean, respectively, the selected harness identifier, a constrained `lowercase slug`
identifier, the supplied relative `POSIX path`, and the `config root` from the
executable harness registry.

A conditional block occupies separate lines:

```text
{{#harness:claude-code,codex}}
Text only for the listed harnesses.
{{/harness}}
```

Names in the condition come only from the closed registry. Duplicates, unknown names,
nested, extra, and unclosed blocks are rejected. Inside fenced code, placeholders and
conditional tags remain literal, so a syntax example is not executed as a template.

`component_root` is never absolute, does not start with `~`, contains neither `..`,
`.` nor a backslash, and is limited to 512 characters. Placeholder values themselves
pass closed validation, so substitution cannot add a new line or control tag.
