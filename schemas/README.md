# Schemas

The generator in `packages/contracts` exports the public models as JSON Schemas in `v1/`.
Use `just back-gen` to regenerate them and `just back-static` to check for drift.

Each schema uses the 2020-12 dialect and a stable `$id` of the form
`urn:ai-stp:schema:v1:<name>`. Value constraints are expressed as patterns and
match the Pydantic model checks; differential tests in `tests/contract/` prove
parity rather than relying on byte comparison alone.

The extension boundary depends on the purpose of the object. Exact references
are hashed structures: unknown fields are rejected (`additionalProperties:
false`). Machine-output envelopes are transit structures: all declared fields
are required on the wire, while unknown optional additions inside a supported
major version are allowed. Strict models remain the producer form; readers use
the `*Reader` classes.
