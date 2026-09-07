# Recover

User intents: it timed out, partial install, stuck operation.

Resolve from machine help: `ai-stp install status`, `ai-stp install recover`,
`ai-stp install resume`.

Establish the actual effect first. Do not repeat `ai-stp install apply` “to
sync”. Use the recovery or resume command the CLI names. Verify with
`ai-stp target status` and `ai-stp install status`.

`ai-stp setup preserve recover` can recover a saved setup identity from the
original plan and fresh provider evidence after a lost response. It does not
repeat installation or turn a partial outcome into a verified one. A new return
plan selects that saved identity. For an environment, use transaction recovery
so compensation follows the recorded reverse order across harnesses.
