---
description: "Fields of the web machine document, paired URLs, and leak prevention."
last_verified: "2026-09-05"
---

# Web machine projection

The requirements owner is `SPEC-036`. This document defines machine fields,
paired URLs, and prohibited data classes. Navigation item composition and page
copy are outside its scope.

## Paired URL

| Projection | Path |
|---|---|
| human | `/{locale}/{path}` |
| machine | `/{locale}/ai/{path}` |

`locale` is `en` or `ru`. The query string belongs to the pair and is not
normalized separately. API endpoints, `/llms.txt`, `/llms-full.txt`,
`/agents.md`, and external URLs are not pages and are not rewritten.

## Inventory entry

| Field | Form |
|---|---|
| `pattern` | human-path segments; `:name` is one segment, `*` is the tail |
| `access` | `public` or `session` |
| `feature` | optional compiled feature key |
| `envGate` | optional runtime gate for the same human page |
| `presenter` | `domain` or `generic` |

Every `page.tsx` in the human tree has exactly one entry. A page without an
entry is a defect.

## Object document

Required component fields: `stable_id`, `version`, `digest`, `harness`,
`component_type`, `trust_lane`, `author_verified`, `component_verified`,
CLI installation command. `component_type` accepts only
`instruction`, `skill`, `mcp`, `hook`, `command`, `agent`, `plugin`, `setting`, `cli`.
A setup returns `purpose` and `target_role` instead of `component_type`.

## Prohibited classes

The document does not include media addresses, `avatar`, `CSRF`, a session token,
a secret, a password, an internal operation identifier, or decorative fields
absent from the human-readable facts on the same page for the same subject.
