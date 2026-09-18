"use client";

import { useId, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
import type { CorporateOverviewNode } from "@/lib/api/generated/types.gen";
import {
  corporateNodeHref,
  overviewEntityIcons as icons,
  overviewAssignmentHref,
  nodeTechnologies,
  type OverviewBranch,
} from "@/lib/corporate-overview";

function OverviewDisclosure({
  label,
  count,
  open,
  onToggle,
  children,
}: {
  label: string;
  count: number;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const panelId = useId();
  return (
    <div className="border-border/70 bg-background/30 min-w-0 rounded-sm border">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        className="hover:bg-muted/60 focus-visible:ring-ring flex min-h-9 w-full items-center justify-between gap-2 px-2 text-left text-xs font-medium focus-visible:ring-2 focus-visible:outline-none"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onToggle();
        }}
      >
        <span className="min-w-0 truncate">
          {label} <span className="text-muted-foreground tabular-nums">({count})</span>
        </span>
        <Icon name={open ? "chevronUp" : "chevronDown"} size="sm" className="shrink-0" />
      </button>
      {open && (
        <div id={panelId} className="border-border/70 space-y-2 border-t p-2">
          {children}
        </div>
      )}
    </div>
  );
}

function AssignmentList({ node }: { node: CorporateOverviewNode }) {
  const t = useTranslations("hub");
  const [all, setAll] = useState(false);
  const [openGroups, setOpenGroups] = useState({ technology: true, component: true, setup: true });
  if (!node.assignments_readable)
    return <p className="text-muted-foreground text-xs">{t("assignmentsRestricted")}</p>;
  const assignments = [
    ...new Map(
      node.assignments.map((item) => [
        `${item.object_kind}:${item.stable_id}:${item.version}`,
        item,
      ]),
    ).values(),
  ];
  const technologies = nodeTechnologies(node);
  const components = assignments.filter((item) => item.object_kind === "component");
  const setups = assignments.filter((item) => item.object_kind === "setup");
  const toggleGroup = (group: keyof typeof openGroups) => {
    setOpenGroups((current) => ({ ...current, [group]: !current[group] }));
  };
  const chipClass =
    "border-border bg-muted/40 text-foreground hover:border-primary hover:bg-muted hover:text-primary focus-visible:ring-ring inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-md border px-2 text-xs transition-colors focus-visible:ring-2 focus-visible:outline-none";
  const technologyChipClass =
    "border-border bg-background/40 text-foreground hover:border-primary hover:bg-muted hover:text-primary focus-visible:ring-ring inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-md border px-2 text-xs transition-colors focus-visible:ring-2 focus-visible:outline-none";
  const renderAssignments = (items: typeof assignments) => (
    <div className="flex flex-wrap gap-2">
      {(all ? items : items.slice(0, 4)).map((item) => (
        <Link
          key={item.assignment_id}
          href={overviewAssignmentHref(item)}
          prefetch={false}
          className={chipClass}
        >
          <Icon name={icons[item.object_kind] ?? "objects"} size="sm" />
          <span className="break-words">{item.display_name || t(item.object_kind)}</span>
        </Link>
      ))}
      {items.length > 4 && !all && (
        <Button
          variant="ghost"
          size="sm"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setAll(true);
          }}
        >
          +{items.length - 4}
        </Button>
      )}
      {items.length > 4 && all && (
        <Button
          variant="ghost"
          size="sm"
          onClick={(event) => {
            event.preventDefault();
            event.stopPropagation();
            setAll(false);
          }}
        >
          {t("showLess")}
        </Button>
      )}
    </div>
  );
  return (
    <div className="grid min-w-0 gap-2 xl:grid-cols-2">
      {technologies.length > 0 && (
        <OverviewDisclosure
          label={t("technologies")}
          count={technologies.length}
          open={openGroups.technology}
          onToggle={() => {
            toggleGroup("technology");
          }}
        >
          <div className="flex flex-wrap gap-2">
            {technologies.slice(0, all ? undefined : 4).map((item) => (
              <Link
                key={item.id}
                href={`/corporate/technologies/${encodeURIComponent(item.id)}`}
                prefetch={false}
                className={technologyChipClass}
              >
                <Icon name="technology" size="sm" />
                <span className="break-words">{item.name}</span>
              </Link>
            ))}
            {technologies.length > 4 && !all && (
              <Button
                variant="ghost"
                size="sm"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setAll(true);
                }}
              >
                +{technologies.length - 4}
              </Button>
            )}
            {technologies.length > 4 && all && (
              <Button
                variant="ghost"
                size="sm"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setAll(false);
                }}
              >
                {t("showLess")}
              </Button>
            )}
          </div>
        </OverviewDisclosure>
      )}
      {components.length > 0 && (
        <OverviewDisclosure
          label={t("aiComponents")}
          count={components.length}
          open={openGroups.component}
          onToggle={() => {
            toggleGroup("component");
          }}
        >
          {renderAssignments(components)}
        </OverviewDisclosure>
      )}
      {setups.length > 0 && (
        <OverviewDisclosure
          label={t("setups")}
          count={setups.length}
          open={openGroups.setup}
          onToggle={() => {
            toggleGroup("setup");
          }}
        >
          {renderAssignments(setups)}
        </OverviewDisclosure>
      )}
      {!technologies.length && !components.length && !setups.length && (
        <p className="text-muted-foreground text-xs">{t("noAssignments")}</p>
      )}
    </div>
  );
}

function employeeIds(branch: OverviewBranch): string[] {
  return branch.node.kind === "employee" ? [branch.node.id] : branch.children.flatMap(employeeIds);
}

export function TreeBranch({
  branch,
  depth,
  level,
  nodes,
  initiallyOpen = false,
}: {
  branch: OverviewBranch;
  depth: number;
  level: number;
  nodes: CorporateOverviewNode[];
  initiallyOpen?: boolean;
}) {
  const t = useTranslations("hub");
  const { node } = branch;
  const employee = node.kind === "employee";
  const [leadOpen, setLeadOpen] = useState(true);
  const leads = node.lead_account_ids.flatMap((id) => nodes.find((item) => item.id === id) ?? []);
  const counts = [
    { kind: "technologies", icon: "technology" as const, count: nodeTechnologies(node).length },
    ...(["component", "setup"] as const).map((kind) => ({
      kind: kind === "component" ? "components" : "setups",
      icon: icons[kind] ?? "objects",
      count: new Set(
        node.assignments.filter((item) => item.object_kind === kind).map((item) => item.stable_id),
      ).size,
    })),
  ];
  const content = (
    <div className="grid min-w-0 flex-1 items-center gap-x-5 gap-y-2 lg:grid-cols-[minmax(18rem,1.1fr)_minmax(12rem,0.8fr)_minmax(20rem,1.5fr)] xl:grid-cols-[minmax(22rem,1.2fr)_minmax(14rem,0.85fr)_minmax(24rem,1.6fr)]">
      <div className="flex min-w-0 items-start gap-4">
        <Icon name={icons[node.kind] ?? "user"} className="mt-0.5" />
        <Badge variant="secondary" className="mt-0.5 shrink-0">
          {t(node.kind)}
        </Badge>
        <div className="min-w-0">
          <Link
            href={corporateNodeHref(node)}
            prefetch={false}
            className="max-w-full text-sm font-medium break-words hover:underline"
          >
            {node.name}
          </Link>
          {!employee && typeof node.description === "string" && node.description && (
            <p className="text-muted-foreground mt-0.5 text-xs">{node.description}</p>
          )}
        </div>
      </div>
      <div className="min-w-0 text-xs">
        {employee ? (
          <p className="text-muted-foreground">
            {typeof node.description === "string" && node.description
              ? node.description
              : typeof node.role === "string"
                ? node.role
                : branch.role === "lead"
                  ? t("lead")
                  : t("staff")}
          </p>
        ) : (
          leads.length > 0 && (
            <OverviewDisclosure
              label={t("lead")}
              count={leads.length}
              open={leadOpen}
              onToggle={() => {
                setLeadOpen((value) => !value);
              }}
            >
              <div className="space-y-2">
                {leads.map((lead) => (
                  <Link
                    key={lead.id}
                    href={corporateNodeHref(lead)}
                    prefetch={false}
                    className="hover:text-primary focus-visible:ring-ring flex items-center gap-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
                  >
                    <span className="bg-muted grid size-7 shrink-0 place-items-center rounded-full text-xs">
                      {lead.name
                        .split(/\s+/)
                        .slice(0, 2)
                        .map((part) => part[0])
                        .join("")}
                    </span>
                    <span className="break-words">{lead.name}</span>
                  </Link>
                ))}
              </div>
            </OverviewDisclosure>
          )
        )}
      </div>
      <div className="min-w-0 space-y-2">
        {!employee && (
          <>
            {node.assignments_readable && (
              <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                {counts.map((item) => (
                  <span
                    key={item.kind}
                    className="inline-flex items-center gap-2 lowercase tabular-nums"
                  >
                    <Icon name={item.icon} size="sm" />
                    {item.count} {t(item.kind)}
                  </span>
                ))}
              </div>
            )}
            <p className="text-muted-foreground max-w-full text-xs">
              {branch.children.length} {t(node.kind === "project" ? "teams" : "employees")}
              {node.kind === "project" &&
                ` · ${new Set(branch.children.flatMap(employeeIds)).size} ${t("employees")}`}
            </p>
          </>
        )}
        {node.kind !== "project" && <AssignmentList node={node} />}
      </div>
    </div>
  );
  return (
    <li
      className={
        level === 0
          ? "border-border bg-card min-w-0 overflow-hidden rounded-lg border"
          : "border-border min-w-0 border-t"
      }
    >
      {employee ? (
        <div className="px-4 py-2 sm:pl-10">{content}</div>
      ) : (
        <details
          open={level === 0 ? depth > 0 : depth > 2 || (depth === 2 && initiallyOpen)}
          className="[&[open]>summary>svg]:rotate-90"
        >
          <summary className="hover:bg-muted focus-visible:ring-ring flex min-w-0 cursor-pointer list-none items-start gap-4 overflow-hidden px-4 py-3 focus-visible:ring-2 [&::-webkit-details-marker]:hidden">
            <Icon name="chevronRight" size="sm" className="mt-1" />
            {content}
          </summary>
          {branch.children.length > 0 && (
            <BranchChildren
              branch={branch}
              depth={depth}
              level={level}
              nodes={nodes}
              initiallyOpen={initiallyOpen}
            />
          )}
        </details>
      )}
    </li>
  );
}

function BranchChildren({
  branch,
  depth,
  level,
  nodes,
  initiallyOpen,
}: {
  branch: OverviewBranch;
  depth: number;
  level: number;
  nodes: CorporateOverviewNode[];
  initiallyOpen: boolean;
}) {
  const t = useTranslations("hub");
  const [all, setAll] = useState(false);
  const children =
    branch.node.kind === "team"
      ? [...branch.children].sort(
          (a, b) =>
            Number(a.role === "lead") - Number(b.role === "lead") ||
            a.node.name.localeCompare(b.node.name),
        )
      : [...branch.children].sort(
          (a, b) =>
            Number(b.role === "owner") - Number(a.role === "owner") ||
            a.node.name.localeCompare(b.node.name),
        );
  const limited = branch.node.kind === "team" && depth < 3 && !all && children.length > 3;
  return (
    <ul className="border-border ml-4 border-l sm:ml-5">
      {(limited ? children.slice(0, 3) : children).map((child, index) => (
        <TreeBranch
          key={child.node.id}
          branch={child}
          depth={depth}
          level={level + 1}
          nodes={nodes}
          initiallyOpen={initiallyOpen && index === 0}
        />
      ))}
      {branch.node.kind === "team" && depth < 3 && children.length > 3 && (
        <li className="border-border border-t px-4 py-1 sm:pl-10">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setAll(!all);
            }}
          >
            {all ? t("showLess") : `+${children.length - 3} ${t("employees")}`}
          </Button>
        </li>
      )}
    </ul>
  );
}
