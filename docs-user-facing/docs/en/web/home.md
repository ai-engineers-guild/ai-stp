---
title: "Home"
description: "The landing page: install the CLI and enter the catalog."
---

# Home

The landing page is the public front door. It states what `ai_stp` is, offers
the catalog, and copies the one supported install command. It does not run
that command, create an account, or write a harness.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/` | anyone |
| Machine | `/{locale}/ai/` | anyone |

`{locale}` is `en` or `ru`. The same facts are on both projections. Signed-in
visitors still see Home; the Sign-in button is hidden for them
(`SignedOutOnly`). There is no extra landing for an authenticated session.

## What this screen is for

Use Home to:

- read the product sentence: a setup registry, not a skill dump;
- copy `uv tool install ai-stp-cli` exactly;
- open the catalog;
- open Sign-in when you have no session.

Home does **not**:

- assemble a setup;
- detect your harness;
- store a model key (the product never needs one);
- start OAuth by itself (Sign-in is a separate page);
- show personalized objects.

The workflow preview behind the hero is decorative. It is not a live
status of your machine.

## What is on the screen

A full-viewport hero, dark even when the rest of the site is light.

| Control | Label | What it does |
| --- | --- | --- |
| Heading | The AI setup registry, not just a skill catalog | product claim |
| Subtitle | Find, verify, install, and earn on AI components. | short pitch |
| Primary button | Browse catalog | goes to `/{locale}/catalog` |
| Secondary button | Sign in | goes to `/{locale}/login`; hidden when signed in |
| Install panel | Install the CLI | copies `uv tool install ai-stp-cli` |
| Copy | Copy / Copied | writes that string to the clipboard |
| Prerequisites | `uv`, `python>=3.12` | what the command expects |

The install hint says: run the command as written; do not assemble it
yourself. The executable is `ai-stp`. The PyPI distribution is
`ai-stp-cli`. `uv tool install ai-stp` installs a different package this
project does not publish.

The Human / Machine switch stays at the bottom of the viewport. Machine
Home is a short Markdown document: the title, the subtitle, a catalog
link, a Documentation link, the install heading, and a fenced copy of
the same command. Documentation there points at `AI_STP_USER_DOCS_URL`
when the presenter is given it; it is not the API OpenAPI page.

Header and footer are the shared chrome described in [Web](index.md).
Header **Documentation** is the external MkDocs host.

Keyboard:

| Shortcut | Action |
| --- | --- |
| `C` | Contact, when `saas_public_pages` is on |
| `P` | Account or Sign-in |
| `Ctrl`/`Cmd` `K` | catalog search, on the catalog page |

## Matching CLI commands

These commands exist in the running CLI registry. Copy them with
`--json`.

```bash
uv tool install ai-stp-cli
ai-stp version --json
ai-stp doctor --json
ai-stp capabilities --json
ai-stp registry search --json
```

`version` reports the running build. `doctor` is a read: it does not
create a device. `capabilities` says which surfaces this build can talk
to. `registry search` reads the public catalog without an account.

After the tool is on `PATH`, the next local identities are created in
the CLI, not on this page:

```bash
ai-stp device init --json
ai-stp passport developer init --json
```

Those commands are documented in [Device](../cli/device.md) and
[Passports](../cli/passport.md). Home never runs them.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| Sign-in button missing | you already have a session | open Account from the header |
| Copy does nothing | the browser blocked the clipboard | select the `<code>` block and copy it |
| `ai-stp` not found after install | `uv` tools are not on `PATH` | see [Troubleshooting](../troubleshooting/index.md) |
| Catalog button works, install fails | Home only copies a string | fix `uv` / Python locally |
| Machine view looks sparse | that is the projection | facts match; chrome is Markdown |
| Contact missing from the header | self-hosted profile | expected; Catalog still works |

Home itself does not 404. A wrong locale prefix 404s the site shell.

If the API is down, Home still renders: it is static chrome plus the
install string. The catalog behind Browse catalog may then show
`The service is temporarily unavailable`.

## What happens after install

The landing command only puts `ai-stp` on the machine. A setup is still
selected and applied in the CLI:

```text
Home copy → uv tool install ai-stp-cli
         → doctor / capabilities
         → registry search
         → select / install plan
         → provider apply
```

Nothing in that chain is a website POST except later sign-in, likes,
reports, and publication confirm.

## Related pages

- [Web map](index.md) — every section and who can see it.
- [Catalog](catalog.md) — search after you click Browse catalog.
- [Sign-in](login.md) — OAuth in the browser and the device code.
- [This documentation](docs.md) — MkDocs host versus `/{locale}/docs`
  versus API `/docs`.
- [Quickstart for people](../quickstart/human.md) — the same install, then
  device and catalog reads.
- [Quickstart for agents](../quickstart/agent.md) — what the agent does
  after the binary is present.
- [CLI](../cli/index.md) — envelopes, mutability, confirmation.
- [Command map](../cli/commands.md) — every declared command.
- [Harnesses](../harnesses.md) — what Home never detects for you.

!!! warning "Do not invent the install line"
    The string on the card is `uv tool install ai-stp-cli`. Changing the
    distribution name, adding a pip extra, or wrapping it in a curl
    one-liner is a different product.
