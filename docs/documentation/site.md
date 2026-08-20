---
description: "Сборка MkDocs и правила навигации."
last_verified: "2026-08-03"
---

# Сайт документации

MkDocs собирает только опубликованную базу знаний репозитория.

Правила:

- strict build;
- navigation выводится из `index.md`;
- Mermaid проверяется отдельно реальным renderer;
- `.site/` не коммитится;
- site build не заменяет проверку ссылок и frontmatter;
- секреты и private runtime data в документацию не включаются.
