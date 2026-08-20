"""Provider protocol v1 and the conformance kit it is checked against (`#169`).

The protocol is declared as data in `protocol` and executed against an
implementation by `conformance`. Keeping the two apart is deliberate: a
conformance kit that also defined the protocol would agree with itself, and the
only thing it would prove is that it can read its own mind.

Provider implementations themselves are separate releases (`REQ-801`), not
modules here.
"""
