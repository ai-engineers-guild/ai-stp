---
description: "Rules for index.md files and generated content tables."
last_verified: "2026-08-03"
---

# Indexes

Every long-lived documentation directory has an `index.md`.

An index contains:

1. frontmatter;
2. one heading;
3. a brief purpose;
4. a generated table of child documents between service markers.

The table is created by `just docs-gen`. Manual editing of the generated block is forbidden. A file absent from the index is considered unavailable for routing and must be added or removed deliberately.
