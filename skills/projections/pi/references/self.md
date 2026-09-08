# Install or refresh the control Skill

Resolve `ai-stp skill status`, `ai-stp skill install` and
`ai-stp skill remove` from the installed machine help.

Choose the directory that the actual harness discovers as a Skill, with the
final directory named `ai-stp`. Use the harness and locale supported by the
installed command descriptor. Install the complete package through the CLI;
copying only SKILL.md loses its playbooks.

Read status, then install. A repeated install refreshes an unchanged owned
package to the version bundled with this CLI. Read status again and verify
ownership, harness, locale and package digest. Refresh the harness's discovery
or start a new session if it still reads an older copy.

`foreign` means the CLI has no ownership claim. `stale` means an owned package
was edited. Inspect and preserve those edits before choosing a separate
installation or an explicitly requested replacement. Do not solve either case
by blindly deleting the directory.

Keep this control Skill available while switching or removing user setups.
It is the agent's procedure for driving the CLI, not the setup being replaced.
