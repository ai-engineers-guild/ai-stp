---
description: "Global CLI configuration fields, defaults, and source precedence."
last_verified: "2026-09-05"
---

# Global CLI configuration

The requirements owner is `SPEC-011`. This document defines the machine boundary: the field set, default values, source precedence, and error rules.

There is one configuration, and it belongs to the user. It contains no secrets and does not replace passports: a passport describes an object; the configuration describes CLI behavior on this device.

## Fields

```yaml
schema_version: 1
catalog:
  enabled: true
  url: "https://ai-stp.aiguild.space"
sync:
  enabled: false
registry:
  path: "${XDG_DATA_HOME}/ai-stp/registry.sqlite"
search:
  result_limit: 20
projects:
  discovery_roots: []
telemetry:
  enabled: false
  url: "https://telemetry.ai-stp.example"
provider:
  paths:
    claude-code: ""
    codex: ""
    pi: ""
    opencode: ""
    grok-build: ""
    cursor: ""
    antigravity: ""
```

| Field | Default | Meaning |
|---|---|---|
| `catalog.enabled` | `true` | Whether to access the public catalog. |
| `catalog.url` | platform address | Base platform address **without the `/v1` prefix**; HTTPS is accepted, as is HTTP for a loopback address. |
| `sync.enabled` | `false` | Whether cloud synchronization is enabled; requires login. |
| `registry.path` | path in the user data directory | Location of the local registry. |
| `search.result_limit` | `20` | Maximum number of candidates in a response. |
| `projects.discovery_roots` | empty list | Explicit roots within which project candidates are searched for. |
| `telemetry.enabled` | `false` | Whether to send the anonymous installation ping. `true` is accepted only after explicit consent; writing it directly is rejected. |
| `telemetry.url` | collector address | Address to which the ping is sent; HTTPS is accepted, as is HTTP for a loopback address, as with `catalog.url`. |
| `provider.paths.antigravity` | empty string | Absolute path to the setup-system provider for `antigravity`. An empty value delegates selection to the registry, then to discovery. |
| `provider.paths.claude-code` | empty string | Absolute path to the setup-system provider for `claude-code`. An empty value delegates selection to the registry, then to discovery. |
| `provider.paths.codex` | empty string | Absolute path to the setup-system provider for `codex`. An empty value delegates selection to the registry, then to discovery. |
| `provider.paths.cursor` | empty string | Absolute path to the setup-system provider for `cursor`. An empty value delegates selection to the registry, then to discovery. |
| `provider.paths.grok-build` | empty string | Absolute path to the setup-system provider for `grok-build`. An empty value delegates selection to the registry, then to discovery. |
| `provider.paths.opencode` | empty string | Absolute path to the setup-system provider for `opencode`. An empty value delegates selection to the registry, then to discovery. |
| `provider.paths.pi` | empty string | Absolute path to the setup-system provider for `pi`. An empty value delegates selection to the registry, then to discovery. |

There are exactly seven `provider.paths` fields, one for each supported harness,
rather than a mapping with an arbitrary key. A mapping whose key can be anything
is not a closed schema: an unknown harness would be accepted, stored, and never
read by anyone. The key is spelled exactly as it is everywhere else
(`claude-code`, not `claude_code`): a second spelling of one identifier is cheap
now and expensive at every subsequent use.

The value is validated when written, not when launched: a relative path, a
symlink in place of an executable file, and a non-executable file are rejected
immediately. A value that is stored cleanly and fails later during installation
is worse than a rejection because the configuration file then appears correct.
Clearing the field is always allowed: making a value harder to remove than to
set would leave the machine bound to a vanished path.

Cleartext is allowed only for a loopback address: `localhost`, `127.0.0.0/8`,
and `::1`. Packets do not leave the machine in this case, so there is nowhere to
intercept them. A local-network address or public name over `http` is still
rejected; this is exactly the case for which the rule exists. Matching is exact:
`localhost.example` is not a loopback address, nor is a numeric notation the
parser does not recognize (`2130706433`, `0177.0.0.1`, `127.1`), even if the
resolver might route it to loopback.

For the deployed environment, the address remains HTTPS through the host's nginx: the
exception applies only to local development and introduces no flag that weakens
the defaults.

The set is closed. An unknown key returns a typed error containing its path and
the set of allowed sibling keys; silently ignoring it is prohibited.

## Source precedence

```text
default value
    ↓
global configuration
    ↓
explicit command argument
```

A command argument applies only to that invocation and does not rewrite the file. The command showing the effective configuration outputs the final value and its source for every field; the source has exactly three values: `default`, `config_file`, `command_argument`.

Writing and overriding are different operations and use different commands. The third precedence tier remains a single-invocation override and does not touch the file; an override is specified as `path=value`, parsed according to the field's declared type, and rejected if the value does not match that type: silently falling back to the default would appear as an applied override.

Writing commands are declared separately: create the file, write a declared field, unset a field, and validate the file. The primary consumer is an agent, so the file is edited by a machine more often than by a person, and saying only that "the user edits the file" is insufficient. All these commands are idempotent, write atomically, and return the effective configuration with the source of every value, so the caller sees both the new value and that it now comes from the file. Creation never overwrites an existing file: every field has a default, no read requires the file to exist, and overwriting would discard settings on which someone may rely.

The file is rewritten in canonical form: sorted keys, the declared schema version, without preserving comments or ordering. This is a deliberate cost. An editor that preserves formatting also preserves what was wrong with it, while deterministic output means that two identically configured installations have byte-for-byte identical files, making any difference between them worth investigating.

The document is validated in full, not only at the top level. An unknown nested key, a section that is a scalar, nesting deeper than declared, and a foreign schema version are rejected with the exact path. Validating only outer keys allowed `catalog.urll`: the section was declared, the key within it was not, the value was discarded, and the response contained the default as though the file had requested it. To an agent, this looks like a successful write that did nothing.

A path value and its display are different things. A field declared as a path is stored and read as an absolute path, while output contracts the home directory to `~` so the account name does not appear in output. The value must not be contracted before use: `~/...` cannot be opened and is resolved relative to the current directory.

## Secrets

The configuration contains no tokens, passwords, or keys. Cloud credentials are stored in the system secure store. Effective-configuration output does not print environment values or expose store contents.

## Offline mode

Offline mode is obtained by disabling `catalog.enabled` and `sync.enabled` and requires no other changes. The set of operations that remain available is owned by `offline-capability.md`.

## Consent to unverified content

The configuration has no consent field for the `experimental` trust line: the `search.include_unverified` key was removed by `ADR-0029`, and indefinite global consent to all unverified content is not supported. Consent is an attribute of a command request or session, while durable records by publisher, object mainline, or authorized task profile are stored as separate records under `unverified-consent.md`, not as a configuration field.
