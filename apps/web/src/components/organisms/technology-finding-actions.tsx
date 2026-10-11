"use client";

import { Button } from "@/components/atoms/button";
import { Menu, MenuTrigger, MenuContent, MenuItem } from "@/components/atoms/menu";
import { Icon } from "@/theme";
import type { TechnologyView } from "@/lib/api/generated/types.gen";
import type { Row, TechnologyReviewState } from "@/lib/technology-review-state";

export function TechnologyFindingActionsMenu({
  state,
  row,
  technology,
  dependency,
  openCreate,
}: {
  state: TechnologyReviewState;
  row: Row;
  technology: TechnologyView | undefined;
  dependency: boolean;
  openCreate: (kind: "technology" | "category") => void;
}) {
  const { mutation, canUpdate, w, setEvidence, setEdit, apply } = state;
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button size="icon" variant="ghost" aria-label={w("actions")}>
          <Icon name="more" size="sm" />
        </Button>
      </MenuTrigger>
      <MenuContent>
        <MenuItem
          onSelect={() => {
            setEvidence(row);
          }}
        >
          {w("evidence")}
        </MenuItem>
        {canUpdate && (
          <>
            {technology && (
              <MenuItem
                onSelect={() => {
                  setEdit(technology);
                }}
              >
                {w("editTechnology")}
              </MenuItem>
            )}
            {dependency ? (
              <MenuItem
                disabled={mutation.busy}
                onSelect={() => {
                  if (technology || row.candidate_technology_id) apply([row], "confirmed");
                  else openCreate("technology");
                }}
              >
                {w("makeTechnology")}
              </MenuItem>
            ) : (
              <>
                <MenuItem
                  onSelect={() => {
                    openCreate("technology");
                  }}
                >
                  {w("createTechnology")}
                </MenuItem>
                <MenuItem
                  disabled={mutation.busy}
                  onSelect={() => {
                    apply([row], "dependency");
                  }}
                >
                  {w("moveToDependencies")}
                </MenuItem>
              </>
            )}
          </>
        )}
      </MenuContent>
    </Menu>
  );
}
