"use client";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { CatalogChoiceMenu } from "@/components/molecules/catalog-choice-menu";
import {
  PeopleCheckbox,
  PeopleRole,
  PeopleTeams,
  PersonIdentity,
} from "@/components/organisms/corporate-people-ui";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import type {
  CorporateContext,
  CorporateInvitation,
  CorporateMember,
} from "@/lib/api/generated/types.gen";
import { isOutstandingInvitation, invitationDisplayState } from "@/lib/corporate-invitation-state";
export function InvitationTable({
  rows,
  context,
  members,
  selected,
  toggle,
  selectPage,
  now,
  canInvite,
  revoke,
}: {
  rows: CorporateInvitation[];
  context: CorporateContext;
  members: readonly CorporateMember[];
  selected: string[];
  toggle: (id: string, checked: boolean) => void;
  selectPage: (checked: boolean) => void;
  now: number;
  canInvite: boolean;
  revoke: (invitation: CorporateInvitation) => void;
}) {
  const t = useTranslations("people");
  return (
    <div
      className="focus-visible:ring-ring min-w-0 overflow-x-auto focus-visible:ring-2 focus-visible:outline-none"
      role="region"
      aria-label={t("invitationsTable")}
      // Keyboard access lets narrow-screen users scroll every table column.
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
    >
      <Table className="min-w-[950px]">
        <THead>
          <Tr>
            <Th className="w-11">
              <PeopleCheckbox
                label={t("selectPage")}
                checked={
                  Boolean(rows.length) && rows.every((row) => selected.includes(row.invitation_id))
                }
                mixed={
                  rows.some((row) => selected.includes(row.invitation_id)) &&
                  !rows.every((row) => selected.includes(row.invitation_id))
                }
                onChange={selectPage}
              />
            </Th>
            {["invitee", "role", "status", "teams", "invitedBy", "sent", "expires", "actions"].map(
              (key) => (
                <Th key={key}>{t(key)}</Th>
              ),
            )}
          </Tr>
        </THead>
        <TBody>
          {rows.map((row) => {
            const state = invitationDisplayState(row, now);
            const teams = context.teams.filter((team) => row.team_ids.includes(team.team_id));
            return (
              <Tr
                key={row.invitation_id}
                data-invitation-state={state}
                className="hover:bg-muted/30"
              >
                <Td className="p-0">
                  <PeopleCheckbox
                    label={t("selectPerson", { name: row.display_name })}
                    checked={selected.includes(row.invitation_id)}
                    onChange={(checked) => {
                      toggle(row.invitation_id, checked);
                    }}
                  />
                </Td>
                <Td className="max-w-72 py-4">
                  <PersonIdentity name={row.display_name} email={row.recipient_email} />
                </Td>
                <Td>
                  <PeopleRole role={row.role} />
                </Td>
                <Td>
                  <Badge
                    variant="outline"
                    className={`border-transparent font-sans font-normal tracking-normal ${state === "accepted" ? "bg-success/15" : state === "revoked" ? "bg-destructive/15" : "bg-warning/15"}`}
                  >
                    {t(state)}
                  </Badge>
                  {row.delivery_state === "failed" ? (
                    <p className="text-destructive mt-1 text-xs">{t("deliveryFailed")}</p>
                  ) : null}
                </Td>
                <Td>
                  {teams.length ? (
                    <PeopleTeams teams={teams} />
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </Td>
                <Td className="whitespace-nowrap">
                  {members.find((member) => member.account_id === row.issuer_account_id)
                    ?.display_name ??
                    row.issuer_account_id ??
                    "—"}
                </Td>
                <Td className="text-muted-foreground whitespace-nowrap tabular-nums">
                  {row.created_at.slice(0, 10)}
                </Td>
                <Td className="text-muted-foreground whitespace-nowrap tabular-nums">
                  {row.expires_at.slice(0, 10)}
                </Td>
                <Td className="text-right">
                  {canInvite && isOutstandingInvitation(row, now) ? (
                    <CatalogChoiceMenu
                      variant="ghost"
                      icon="more"
                      label={t("personActions", { name: row.display_name })}
                      align="end"
                      options={[
                        {
                          label: t("revokeInvitation"),
                          onSelect: () => {
                            revoke(row);
                          },
                          icon: "close",
                        },
                      ]}
                    />
                  ) : (
                    <span className="text-muted-foreground px-4">—</span>
                  )}
                </Td>
              </Tr>
            );
          })}
          {!rows.length ? (
            <Tr>
              <Td colSpan={9} className="text-muted-foreground py-14 text-center">
                {t("noMatchingInvitations")}
              </Td>
            </Tr>
          ) : null}
        </TBody>
      </Table>
    </div>
  );
}
