# Environment

User intents: configure this project, prepare several harnesses, install the
programs and tools needed by selected setups.

Start the `install` intent once per harness setup. Do not type
`environment plan`, `environment inspect`, `install transaction plan`,
`install transaction approve`, or `install transaction apply`. Multi-root
coordination is expert recovery:
follow [recover](recover.md) when an aggregate already exists.

Inspect the project with the `inspect` intent first only when the user asked
what is wrong. Keep each setup attached to its own harness. Program evidence,
authorization, and verified native configuration are separate facts.

Shared executable versions remain separate from a harness's native snapshot.
Returning one setup never authorizes deleting a shared tool or another
project's runtime. Remaining toolchain and harness-program leaves stay in
machine help.
