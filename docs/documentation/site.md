---
description: "MkDocs build and navigation rules."
last_verified: "2026-08-03"
---

# Documentation Site

MkDocs builds only the repository's published knowledge base.

Rules:

- strict build;
- navigation is derived from `index.md`;
- Mermaid is checked separately with a real renderer;
- `.site/` is not committed;
- the site build does not replace link and frontmatter checks;
- secrets and private runtime data are not included in documentation.
