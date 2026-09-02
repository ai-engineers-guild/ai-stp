---
description: "Automated checks for documentation and work packages."
last_verified: "2026-09-02"
---

# Documentation Checks

The checks cover:

- valid frontmatter;
- absence of unfilled placeholders;
- links and anchors;
- index completeness and parity;
- Markdown/YAML/Mermaid syntax;
- English prose outside code and identifiers, except the explicit localized
  GitHub homepage `README.ru.md`;
- absence of task state in `docs/`;
- required sections in active specs, requirement uniqueness, and linkage to an acceptance oracle;
- unit tests for the validators themselves;
- strict MkDocs build.

A failing check is not fixed by disabling the rule. Valid remedies are fixing the source, fixing a reproducibly incorrect validator, or recording temporary technical debt with an owner and an observable retirement condition.
