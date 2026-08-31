---
description: "Decision to make the public profile a separately authored object rather than a passport projection."
last_verified: "2026-08-04"
---

# ADR-0023: The public profile is a separately authored object

Status: accepted. Supersedes `ADR-0010`.

## Context

`ADR-0010` correctly separated the public profile from the developer passport and prohibited a public-visibility flag inside the passport. Projection was selected as the mechanism: the user marks which passport fields to display.

The projection has a systemic defect. A passport describes the working environment: installed harnesses and their versions, tools, habits, and selection history. None of these fields is what a person wants to write publicly about themselves. Selecting passport fields therefore yields either an empty profile or publication of work details that the user did not intend to disclose.

There is a second problem: the relationship remains live. With a projection, changing the passport changes the public profile. The user updates a tool version locally and, without making any decision about public visibility, changes the public page.

## Options

1. Retain projection with field selection. This requires no changes but binds local working state to the public page and poorly serves the profile's purpose.
2. Retain projection but freeze values at selection time. This removes the live relationship but retains an unsuitable field set and adds the question of updating the snapshot.
3. Make the public profile an independent object that the user or their agent authors separately.

## Decision

Option 3 is accepted.

**The public profile is a separate object.** It is not a projection of the developer passport. Fields are not copied from the passport and are not updated from it automatically.

**Authoring is always explicit.** The profile is created and changed by a separate action of the user or their agent. Changing the passport does not change the profile; changing the profile does not change the passport.

**An empty profile means there is no public profile.** Until the user has authored anything, there is no public page; this is not an empty card or partial disclosure.

**The passport remains private.** `DeveloperPassport` remains the private canonical source of working context and has no public-visibility flag. Preventing leakage of private fields remains a mandatory negative check.

**The profile remains linked to authorship.** Published objects reference the author's account; the profile gives that account a public representation but is not evidence of author verification.

## Consequences

- `ADR-0010` gains superseded status and links here;
- `SPEC-003` replaces the projection-policy requirement with a requirement for a separate object and explicit authoring;
- `SPEC-013` describes the public profile as an independent data-management object;
- `architecture/domain-model.md` no longer calls `PublicProfile` a projection;
- the web and CLI edit the profile through one application scenario under `ADR-0018`;
- a negative check confirms that changing the passport does not alter any field of the public profile.

## Reconsideration conditions

The decision shall be reconsidered if users begin manually duplicating in the profile the same data already present in the passport, and that duplication proves persistent and widespread.
