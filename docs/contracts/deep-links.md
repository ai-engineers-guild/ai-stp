---
description: "Grammar of canonical URLs and CLI references for component, setup, publisher, and report intent."
last_verified: "2026-08-15"
---

# Canonical CLI/web deep links

The requirements owner is `SPEC-030`; the decision is `ADR-0064`. This document
defines the machine grammar `deep_link_v1`.

## Normalized target

| Field | Form |
|---|---|
| `grammar_version` | `1` |
| `kind` | `component`, `setup`, or `publisher` |
| `stable_id` | canonical ID with the prefix corresponding to `kind` |
| `version` | optional exact canonical `X.Y`; component/setup only |
| `locale` | `ru` or `en`; default `ru` |
| `intent` | `view` or `report`; `report` requires component/setup and version |

## URL paths

```text
/{locale}/catalog/components/{component_id}
/{locale}/catalog/components/{component_id}/versions/{X.Y}
/{locale}/catalog/setups/{setup_id}
/{locale}/catalog/setups/{setup_id}/versions/{X.Y}
/{locale}/publishers/{account_id}
```

`report` uses the exact component/setup version path and the fixed `#report`
fragment. Query is absent in all forms. The base address is the current
`catalog.url` without `/v1`; its optional base path is preserved before the route.

## CLI reference

The canonical form is an argument array, not a shell string:

```json
[
  "ai-stp", "link", "web",
  "--kind", "component",
  "--id", "component_01JQZK7B8N4M6P2R9T5V0X3Y7Z",
  "--version", "1.2",
  "--locale", "ru",
  "--json"
]
```

For `report`, `--report` is added before `--json`. The human `cli_command` is
formed only by joining the safe elements of the canonical array with spaces.
Omitting `--locale` is allowed in CLI input, but canonical output always includes
the resolved locale.

## Validation and access

The stable ID and version are validated before the URL is built. The parser
accepts only the precisely configured scheme, authority, and base path, the
listed paths, and the `report` fragment in an allowed context. Credentials,
query, encoded separators, extra segments, and unknown fragments are rejected.

Generation and parsing read nothing from the catalog. A link is not proof of
existence or access: public visibility, authorization for private objects, and enumeration
prevention remain behind the existing web/API boundary.

The web consumer uses the same packaged corpus and the same grammar. It is not a
second owner of the routes.
