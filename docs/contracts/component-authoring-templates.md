---
description: "Versioned scaffold plans and safe projection of component authoring templates."
last_verified: "2026-08-29"
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

`component scaffold apply` accepts the same inputs, the exact
`--expected-plan-digest`, and `--confirm`. The CLI rebuilds the plan, reserves a new
directory without overwriting, and creates files with mode `0600`, rolling back its
own incomplete result on failure. An existing target—even an empty one—a symlink,
and a missing parent are rejected; there is no hidden overwrite or merge.

Declarative `instruction`, `skill`, `command`, `agent`, and `setting` use
`--language none`. Executable `mcp` and `plugin` select `python`, `typescript`,
`javascript`, `rust`, `go`, or `dart-flutter`; `hook` does not accept Rust or Go
because the provider does not perform a hidden source build. The variant is `portable`
or one of the harnesses in the closed registry. If the selected harness has no
independent native form for the type, the plan fails closed before any write.

The `component-scaffold/2` version directory contains `component-passport.json`, `eval-profile.json`, a descriptor,
portable authoring-template.md, README, safety declaration, publication checklist,
and a ready native layout under `native/`. The passport is a local patch: it contains
no invented source, secrets, or permission to redistribute. The author continues via
`component passport validate`, local registration, and publication plan commands.

For a hook, canonical `hook-source.json` stores the event, order, blocking failure
policy, and handler command; the strict schema prohibits extra fields. It
deterministically produces `native/hooks.json` and an adjacent executable handler.
Manifest-directory plugins receive a product manifest. OpenCode and Pi receive a
single JS/TS module without an invented manifest. Marketplace registration is not a
plugin package: it is a separate `setting` that owns an entire native settings file.
A Codex agent does not exist as a standalone component and is rejected instead of
being converted into another type.

## Author path

1. Run `component scaffold plan`, review the descriptor, every file, and digest,
   then pass unchanged inputs to `component scaffold apply` with the exact plan
   digest and `--confirm`.
2. Implement the behavior and fill in only confirmed patch facts. For `required_env`,
   record names and purposes, but not values. Add source only after pinning a public
   GitHub commit.
3. Place the component in a supported native layout, run `component discover` and
   `component adopt`, then apply the patch through
   `component passport update --expected-revision ... --from ... --confirm`.
4. Run `component passport validate` and the evaluation lifecycle. The saved profile
   shows in advance that core will perform local-static checks, while model/human
   checks without the corresponding runner will honestly remain `not_run`.
5. Record and release an exact version, then use `publication plan` and
   `publication confirm`. The publication checklist is not authorization: source,
   license, evidence, and server-side validation remain mandatory separate boundaries.

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
