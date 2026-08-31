# Legal policy source

This directory is the public source of legal text served by ai_stp.

```text
docs-user-facing/legal/{locale}/{document-slug}/{policy-version}/document.md
```

Each `document.md` contains frontmatter with `slug`, `kind`, `locale`, `title`,
`policy_version`, and `effective_at`. A published version is immutable: never
edit it after users have accepted it. Copy it to a new version directory,
update the frontmatter and text, add the new path to `builtin.py`, and retain the
old file so accepted revisions remain auditable.

At service startup, the repository-tracked Markdown is rendered and stored as
an immutable database revision together with its source path and deployed Git
commit. The public site shows the rendered text and links to that exact source
on GitHub. Runtime configuration must not alter legal content.
