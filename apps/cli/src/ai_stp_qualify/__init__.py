"""Agent qualification harness that runs from a source checkout only.

`agy` drives a real agent binary through the qualification scenarios and
`identity` binds each measured cell to the exact code and Skill it ran
against. Both resolve the repository from their own location and spawn
agents, so neither belongs in what users install: this package sits beside
`ai_stp_cli` in `apps/cli/src` — importable through the workspace's editable
path — and is outside the wheel (`packages = ["src/ai_stp_cli"]`), the sdist
and the desktop sidecar (`--collect-all ai_stp_cli`). The shipped `qualify`
command reports unrun cells and never imports it.

Running real-agent corpora is an explicit owner decision; nothing in the gate
invokes this package against a live model.
"""
