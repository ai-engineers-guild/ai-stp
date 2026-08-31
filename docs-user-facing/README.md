# Public user-facing source

This directory is the canonical repository source for content published to users.

- `content/` contains localized content-hub articles. A deployment builds an exact-commit
  snapshot and imports immutable revisions into PostgreSQL before the web service starts.
- `docs/` contains localized product and CLI documentation rendered by the documentation
  service and the web documentation routes.
- `legal/` contains localized, versioned legal policies synchronized into immutable database
  revisions when the API starts.

The internal `docs/` directory remains the normative engineering corpus. Do not create tracked
copies of these sources under an application directory. Build images may copy the canonical
files into an image, but runtime readers and source links must retain the paths below this root.
