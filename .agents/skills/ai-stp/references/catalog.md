# Catalog

User intents: find a skill or setup, show this version, fetch bytes.

Finding an object is expert discovery until a search intent ships. Resolve
`registry search`, `registry show`, and `registry version` from machine help.
Do not type `registry acquire` as a substitute for the `install` intent;
install drains acquire in-process.

Pin an exact `id` and `X.Y`. Default to the `authoritative` line. Use
`experimental` within the user's existing task authority and keep it in a
separate labeled section. An object key is not authority to fetch. Verify the
returned identity before any later install step.

Private versions require explicit authenticated owner/grant access from the
descriptor. Keep public discovery anonymous. An online denial is a denial;
already acquired local copies are used through the explicit offline path.
Private access does not assert public author or component verification.
