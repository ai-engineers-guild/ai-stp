---
title: "Contact"
description: "The public contact page in the saas profile."
---

# Contact

Contact stores a message so the operators can reply. It is a public
form on the SaaS profile (`saas_public_pages`). It is not a live chat,
not a ticket console, and not the report form for a catalog version.

## URLs and who can see them

| Projection | URL | Who can see it |
| --- | --- | --- |
| Human | `/{locale}/contact` | anyone, if flagged |
| Machine | `/{locale}/ai/contact` | anyone, if flagged |

The header icon (shortcut `C`) and the footer **Contact** link both go
here. Self-hosted builds compile `saas_public_pages` off: the control
disappears and the route is not part of the public nav.

Anyone may submit, signed-in or not. A session is not attached as
identity on this form. Reports against an exact catalog version still
belong on [Reports](reports.md) after sign-in, or on a card's Report
action which pre-fills kind, id, version, and digest.

## What this screen is for

Use Contact to ask about the catalog, publishing, providers, or safe
installation when you do not have an exact object digest.

Use a catalog **Report** when you are pointing at one immutable
version. Use GitHub issues only if you are contributing to the
repository, not for account secrets.

Contact does **not**:

- reset a password (there is none; OAuth is the sign-in);
- merge accounts;
- accept attachments;
- file a staff moderation case you can watch;
- bypass publication gates.

## What is on the screen

Two columns on wide viewports: sticky intro, then the form card.

| Field | Label | Rules |
| --- | --- | --- |
| Name | Name | required, max 120 |
| Reply email | Reply email | required, email, max 254 |
| Subject | Subject | required, max 160 |
| Message | Message | required, min 10, max 4000 |
| Submit | Send message | disabled while pending or after success |

Hints on the page:

- The message is stored with the reply email you provide. Do not
  include secrets.
- Include the public URL, `stable_id`, or exact version when the
  question concerns a catalog object.
- Do not include secrets, tokens, private keys or private repository
  content.

The same form component can be opened as a report dialog from a catalog
card with `targetKind` `component`, `setup`, or author. On `/contact`
itself the target is `other` / `contact`.

After a successful POST the button stays disabled and the page shows
that the complaint was accepted. Rate limits return
`Too many complaints. Try again later.` Other failures:
`The complaint could not be sent.`

Human / Machine switch: machine Contact is a short document with the
title, subtitle, and a link back. It does not embed a fillable form.

## Matching CLI commands

Catalog reports have a CLI path. The public contact form does not.

```bash
ai-stp report preview --json
ai-stp report confirm --json
ai-stp report list --json
```

`report preview` prepares a bounded payload without sending it.
`report confirm` submits one exact preview after an explicit flag.
`report list` lists **your** closed cases (signed-in CLI). That is the
twin of [Reports](reports.md), not of this page.

There is no `ai-stp contact` command. Do not pipe a message into
`report confirm` to “contact support”.

## Dead-ends

| What you see | What it means | What to do |
| --- | --- | --- |
| No Contact in the header | `saas_public_pages` off | use GitHub for the repo, CLI for object reports |
| Send stays disabled | already submitted in this view | reload to send another |
| Too many complaints | rate limit | wait; do not retry in a loop |
| The complaint could not be sent | API or validation | check email format; remove secrets; retry later |
| No case id on this page | contact is not the reports ledger | look at Reports after sign-in if you filed from a card |
| Operator never replies to a secret | you sent a token | rotate the token; do not resend it here |
| Shortcut `C` does nothing | flag off, or focus in an input | expected on self-hosted |

Do not paste `.env` files, session cookies, provider tokens, or private
keys. The privacy hint is a rule, not decoration.

## Contact vs Report vs GitHub

| Need | Page | Needs digest? | Needs session? |
| --- | --- | --- | --- |
| Question about the product | this page | no | no |
| This exact version is harmful | [Reports](reports.md) | yes | yes |
| Catalog card Report | pre-filled Reports | yes | yes |
| Patch to the repository | GitHub | n/a | GitHub account |
| Legal processing question | this page or [Legal](legal.md) | no | no |

The stored fields are name, reply email, subject, message, and the
internal target (`other` / `contact` on this URL). There is no
attachment slot, so logs and screenshots have to be described, not
uploaded. Prefer a public catalog URL over a paste.

Rate limit is per client, not a daily quota shown in the UI. When it
fires, wait. Looping Send will extend the lockout.

Machine Contact has no form. An agent should not invent a POST; point
a human at this URL or use `report preview` when the object is known.

Shortcut `C` is the same URL as the header icon. It does nothing when
`saas_public_pages` is off. After a successful send, reload the page
if you need a second message; the disabled button is per view, not a
lifetime lock.

## Related pages

- [Reports](reports.md) — signed-in cases against an exact digest.
- [Legal](legal.md) — Privacy and service rules.
- [Catalog](catalog.md) — copy `stable_id` before writing.
- [This documentation](docs.md) — how-tos that may already answer.
- [CLI reports](../cli/report.md) — preview then confirm.
- [Trust and safety](../trust-and-safety/index.md) — what to report.

!!! warning "Secrets"
    A message that contains a password, token, or private key is a
    leak. Rotate the credential. Write the public URL and `stable_id`
    instead.
