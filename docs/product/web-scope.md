---
description: "The web MVP scope and the ownership boundary between the web and CLI."
last_verified: "2026-08-17"
---

# Web MVP

The web owns the account and public catalog. The CLI and agent own creation, assembly, verification, and installation. The boundary follows ownership, not volume: the decision belongs to `ADR-0018`. Under `ADR-0035`, the web is available in Russian and English from launch.

## Public area

- landing and installation command;
- sign-in through Google and GitHub;
- public catalog search;
- setup and component cards with versions, compatibility, and a verification summary;
- passports for published versions;
- public author profiles.

Public routes for the landing page, catalog, object card, sign-in, and basic
account pages remain usable at 360–430 px in `ru` and `en`: the actions for
installation and viewing sources are visible, the document does not overflow
horizontally, and mobile navigation and result refinement are keyboard-accessible.
The executable criteria belong to `SPEC-022`, `SPEC-023`, `SPEC-034`, and
`SPEC-037`.

## After sign-in

- account profile;
- public profile and privacy settings;
- devices, their state, and revocation;
- the user's own drafts, objects, and versions;
- publication and its state;
- synchronization state;
- granting access by account identifier and invitations by verified email;
- revoking grants and invitations;
- reporting an object and the state of the user's own reports;
- minimal administrative actions with mandatory auditing, including report triage.

## Owned by the CLI and agent

Creating and changing developer and project passports, project indexing, searching for and selecting candidates, setup assembly, verification, and installation are performed through the CLI. The web displays the results of these operations but does not perform them.

## Not in the MVP

A browser-based setup editor, social features, payments, an enterprise interface, and a runtime telemetry panel are not part of the MVP.

## One implementation of the rules

The web and CLI invoke one application scenario and one API. A separate web route is permitted only when it has its own security rationale, and that rationale is recorded. A second implementation of business rules is prohibited: it doubles the authorization surface and creates behavioral divergence between clients.
