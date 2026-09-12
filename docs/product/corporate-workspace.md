---
description: "Interaction contract for corporate team and employee management."
last_verified: "2026-09-12"
---

# Corporate team workspace

This is an Operate surface inside the existing ai_stp visual system. A corporate
administrator opens a team to understand its purpose, roster, and leadership and
assign employees without typing identifiers. Employees and leads read only the
relationships authorized by the server.

The first viewport presents the team name, description, state, an action menu, and
the roster. Employee names and team roles are the primary content. Technical IDs
and revisions are collapsed. Empty teams explain the next action; archived teams
explain why assignments are unavailable. The existing neutral surfaces, typography,
signal-orange primary action, theme preference, and icon registry are preserved.

Editing is an explicit inline state entered from the menu, with name, optional
description, save, and cancel. Archive/restore is a separate action. Cancel never
saves draft values through a later lifecycle action.

The assignment chooser supports name search, existing membership context,
unassigned filtering, multiple selection, and a staff/lead role scoped to the team.
Employee details expose the same relationships from the employee's perspective.
The workspace directory searches employees and filters by a selected team or no
team. Organization roles come from their list endpoint and remain separate.

The signature interaction is progressive assignment: the roster stays visible while
the administrator selects additions inline. Success refreshes relationships; partial
failure retains only unfinished choices with their original idempotency keys.
Loading disables mutations, errors preserve input, and cancel returns to reading.
All controls remain keyboard accessible and layouts wrap at mobile widths.

Data ranges use the existing bounded contracts: up to 256 visible members and
teams, names up to 200 characters, descriptions up to 2000 characters. No invented
member, role, or permission data is displayed. SPEC-079 owns authorization and
lifecycle behavior; this document owns interaction and hierarchy.
