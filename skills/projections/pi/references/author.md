# Author

To register a local directory as a component, start the `author` intent.
Do not type `ai-stp component adopt`, `ai-stp component scaffold plan`,
`ai-stp component scaffold apply`, `ai-stp setup compose apply`, or
`component materialize plan`.
The engine freezes the directory as one embedded component and one new
setup identity. It does not install the setup and does not mutate a saved
setup in place.

1. Pass `directory`, `harness_id`, `component_type`, `name`, and
   `license_spdx` when known. Kinds come from `COMPONENT_TYPES` filtered
   by that harness's native surfaces. Omitted fields become one typed
   question each.
2. Call `ai-stp task start` with intent `author` and execute continuation
   `argv` only when `actor` is `cli`. Relay one blocked question through `ai-stp task answer`.
3. Report the component id, the new setup id, and whether a new identity
   was minted. Envelope `ok` alone is not enough. Install that pin with
   the `install` intent when the user wants it on a target.

Scaffold, adopt, validate, and release stay expert. Resolve those families
from machine help; do not type their plan/apply leaves. Publicity is a
separate user decision: start the `publish` intent after `author`. Do not
type `ai-stp publication plan`, `ai-stp publication confirm`,
`setup publish plan`, or `setup publish confirm`. Provenance
is the local filesystem; do not invent git history. Do not type a
`github.com` remote. New publications default
to private. A worker receipt is not a readable catalog result unless outcome
`readable` is true.
