# Schemas

This directory contains generated JSON Schemas, the machine owners of the
contracts defined by `SPEC-015`.

Files in `v1/` are created only by the generator from the `ai-stp-foundation`
Pydantic models and must not be edited by hand:

```bash
just back-gen       # regenerate schemas/v1 and Skill projections
just back-static    # compare byte-for-byte with the models; part of just check
```

Drift between the models and committed files fails `back-static` in CI under
`SPEC-015` REQ-1509. A schema without a generator in `v1/` is also an error.
The canonical contracts in `docs/contracts/` explain the fields; this directory
contains machine artifacts only.

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
