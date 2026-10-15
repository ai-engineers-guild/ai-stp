"use client";

import { Button } from "@/components/atoms/button";
import { Menu, MenuTrigger, MenuContent, MenuItem } from "@/components/atoms/menu";
import { EntityActionItems } from "@/components/organisms/entity-action-items";
import { Icon } from "@/theme";
import type { TechnologyView } from "@/lib/api/generated/types.gen";
import type { Row, TechnologyReviewState } from "@/lib/technology-review-state";

export function TechnologyFindingActionsMenu({
  state,
  row,
  technology,
  openCreate,
}: {
  state: TechnologyReviewState;
  row: Row;
  technology: TechnologyView | undefined;
  dependency: boolean;
  openCreate: (kind: "technology" | "category") => void;
}) {
  const { mutation, w, setEvidence, setEdit, apply } = state;
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button size="icon" variant="ghost" aria-label={w("actions")}>
          <Icon name="more" size="sm" />
        </Button>
      </MenuTrigger>
      <MenuContent>
        <EntityActionItems
          subject={{
            kind: "finding",
            id: row.scan.scan_id,
            organization_id: state.authority.organizationId,
            finding_kind: row.kind,
            coordinate: row.coordinate,
            usage_context: row.context,
          }}
          entries={{
            evidence: (
              <MenuItem
                onSelect={() => {
                  setEvidence(row);
                }}
              >
                {w("evidence")}
              </MenuItem>
            ),
            edit_technology: (
              <MenuItem
                onSelect={() => {
                  if (technology) setEdit(technology);
                }}
              >
                {w("editTechnology")}
              </MenuItem>
            ),
            make_technology: (
              <MenuItem
                disabled={mutation.busy}
                onSelect={() => {
                  if (technology || row.candidate_technology_id) apply([row], "confirmed");
                  else openCreate("technology");
                }}
              >
                {w("makeTechnology")}
              </MenuItem>
            ),
            create_technology: (
              <MenuItem
                onSelect={() => {
                  openCreate("technology");
                }}
              >
                {w("createTechnology")}
              </MenuItem>
            ),
            move_to_dependencies: (
              <MenuItem
                disabled={mutation.busy}
                onSelect={() => {
                  apply([row], "dependency");
                }}
              >
                {w("moveToDependencies")}
              </MenuItem>
            ),
          }}
        />
      </MenuContent>
    </Menu>
  );
}
