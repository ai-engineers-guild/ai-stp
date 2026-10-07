"use client";
import type { Dispatch, SetStateAction } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { CatalogChoiceMenu } from "@/components/molecules/catalog-choice-menu";
import {
  PeopleCheckbox,
  PeopleRole,
  PeopleTeams,
  PersonIdentity,
} from "@/components/molecules/people-ui";
import { Table, TBody, Td, THead, Th, Tr } from "@/components/atoms/table";
import type { CorporateMember, CorporateContext } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

function activityLabel(value: string | null | undefined, now: string, locale: string) {
  if (!value) return "—";
  const seconds = (Date.parse(value) - Date.parse(now)) / 1000;
  if (!Number.isFinite(seconds)) return "—";
  const [unit, divisor] =
    Math.abs(seconds) < 3600
      ? (["minute", 60] as const)
      : Math.abs(seconds) < 86400
        ? (["hour", 3600] as const)
        : (["day", 86400] as const);
  return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(
    Math.round(seconds / divisor),
    unit,
  );
}

function MemberRow({
  member,
  context,
  selected,
  toggle,
  now,
}: {
  member: CorporateMember;
  context: CorporateContext;
  selected: boolean;
  toggle: (checked: boolean) => void;
  now: string;
}) {
  const t = useTranslations("people");
  const locale = useLocale();
  const name = member.display_name ?? member.account_id;
  const profile = `/corporate/employees/${encodeURIComponent(member.account_id)}`;
  const canInspect = context.capabilities.some((permission) =>
    ["member.update", "member.delete"].includes(permission),
  );
  const teams = context.teams.filter((team) =>
    team.members.some((entry) => entry.account_id === member.account_id),
  );
  return (
    <Tr className="hover:bg-muted/30 transition-colors" data-selected={selected || undefined}>
      <Td className="p-0">
        <PeopleCheckbox label={t("selectPerson", { name })} checked={selected} onChange={toggle} />
      </Td>
      <Td className="max-w-64">
        <Link
          href={profile}
          className="focus-visible:ring-ring block rounded-sm hover:underline focus-visible:ring-2 focus-visible:outline-none"
        >
          <PersonIdentity name={name} you={member.account_id === context.member.account_id} />
        </Link>
      </Td>
      <Td>
        {member.contact_email ? (
          <a
            className="text-muted-foreground hover:text-foreground hover:underline"
            href={`mailto:${member.contact_email}`}
          >
            {member.contact_email}
          </a>
        ) : (
          <Badge variant="outline" className="text-muted-foreground font-sans font-normal">
            {t("noEmail")}
          </Badge>
        )}
      </Td>
      <Td className="whitespace-nowrap">{member.job_title_name ?? "—"}</Td>
      <Td className="max-w-72">
        <PeopleTeams teams={teams} />
      </Td>
      <Td>
        <PeopleRole role={member.role} />
      </Td>
      <Td>
        <Badge
          variant="outline"
          className={`border-transparent font-sans font-normal tracking-normal ${member.state === "active" ? "bg-success/15" : "bg-warning/15"}`}
        >
          {t(member.state)}
        </Badge>
      </Td>
      <Td className="text-muted-foreground whitespace-nowrap tabular-nums">
        {member.joined_at?.slice(0, 10) ?? "—"}
      </Td>
      <Td className="text-muted-foreground whitespace-nowrap">
        {activityLabel(member.last_activity_at, now, locale)}
      </Td>
      <Td className="text-right">
        <CatalogChoiceMenu
          icon="more"
          variant="ghost"
          align="end"
          label={t("personActions", { name })}
          options={[
            { label: t("viewProfile"), href: profile, icon: "user" },
            ...(canInspect
              ? [
                  {
                    label: t("manageAccess"),
                    href: `/corporate/organization/admins/employees/${encodeURIComponent(member.account_id)}`,
                    icon: "access" as const,
                  },
                ]
              : []),
          ]}
        />
      </Td>
    </Tr>
  );
}

export function CorporateMembersTable({
  rows,
  context,
  selected,
  setSelected,
  now,
  sort,
  update,
  empty,
}: {
  rows: CorporateMember[];
  context: CorporateContext;
  selected: string[];
  setSelected: Dispatch<SetStateAction<string[]>>;
  now: string;
  sort: string;
  update: (name: string, value: string) => void;
  empty: boolean;
}) {
  const t = useTranslations("people");
  return (
    <div
      className="focus-visible:ring-ring min-w-0 overflow-x-auto focus-visible:ring-2 focus-visible:outline-none"
      role="region"
      aria-label={t("membersTable")}
      // Keyboard access is required for scrolling the table on narrow viewports.
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
    >
      <Table className="min-w-[1100px]">
        <THead>
          <Tr>
            <Th className="w-11">
              <PeopleCheckbox
                label={t("selectPage")}
                checked={
                  Boolean(rows.length) &&
                  rows.every((member) => selected.includes(member.account_id))
                }
                mixed={
                  rows.some((member) => selected.includes(member.account_id)) &&
                  !rows.every((member) => selected.includes(member.account_id))
                }
                onChange={(checked) => {
                  setSelected((current) =>
                    checked
                      ? [...new Set([...current, ...rows.map((member) => member.account_id)])]
                      : current.filter((id) => !rows.some((member) => member.account_id === id)),
                  );
                }}
              />
            </Th>
            {[
              "nameColumn",
              "contact",
              "jobTitle",
              "teams",
              "role",
              "status",
              "joinedColumn",
              "lastActivity",
            ].map((key) => (
              <Th key={key}>
                {key === "joinedColumn" ? (
                  <button
                    type="button"
                    className="focus-visible:ring-ring inline-flex items-center gap-1 rounded-sm focus-visible:ring-2 focus-visible:outline-none"
                    onClick={() => {
                      update("sort", sort === "joined_desc" ? "joined" : "joined_desc");
                    }}
                  >
                    {t(key)}
                    <Icon name={sort === "joined" ? "chevronUp" : "chevronDown"} size="sm" />
                  </button>
                ) : (
                  t(key)
                )}
              </Th>
            ))}
            <Th className="relative w-11">
              <span className="sr-only">{t("actions")}</span>
            </Th>
          </Tr>
        </THead>
        <TBody>
          {rows.map((member) => (
            <MemberRow
              key={member.account_id}
              member={member}
              context={context}
              now={now}
              selected={selected.includes(member.account_id)}
              toggle={(checked) => {
                setSelected((current) =>
                  checked
                    ? [...current, member.account_id]
                    : current.filter((id) => id !== member.account_id),
                );
              }}
            />
          ))}
          {!rows.length ? (
            <Tr>
              <Td colSpan={10} className="text-muted-foreground py-14 text-center">
                {t(empty ? "noMembers" : "noMatchingMembers")}
              </Td>
            </Tr>
          ) : null}
        </TBody>
      </Table>
    </div>
  );
}
