# Catalog

User intents: find a skill or setup, show this version, fetch bytes.

Do not type `registry search` or `registry acquire`. Do not type
`registry port discover`, `registry port inspect`, `registry port plan`, or
`registry port import`. Do not type `registry show`, `registry fetch`, or
`registry version` for ordinary setup. Catalog bytes for an
everyday install go through the `install` intent. Identity inspect stays
expert machine help when the user asked what an object is, not how to install it.

Pin an exact `id` and `X.Y`. Default to the `authoritative` line. Use
`experimental` within the user's existing task authority and keep it in a
separate labeled section. An object key is not authority to fetch. Verify the
returned identity before any later install step.

Private versions require explicit authenticated owner/grant access from the
descriptor. Keep public discovery anonymous. An online denial is a denial;
already acquired local copies are used through the explicit offline path.
Private access does not assert public author or component verification.
