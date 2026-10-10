/* eslint-disable max-lines -- Job-title table, detail panel, and assignment dialogs stay in one render owner. */
"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { corporateMutation } from "@/lib/api/corporate-mutation";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Textarea } from "@/components/atoms/textarea";
import { CatalogChoiceMenu } from "@/components/molecules/catalog-choice-menu";
import { FormDialog } from "@/components/molecules/form-dialog";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import {
  CorporateDetailDrawer,
  PeoplePager,
  PeopleSearch,
  PeopleSelect,
  PeopleTable,
  PersonIdentity,
  peopleCellClass,
  peopleHeadClass,
  usePeopleFilters,
} from "@/components/organisms/corporate-people-ui";
import type { CorporateJobTitleView, CorporateMember } from "@/lib/api/generated/types.gen";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";

type Props = {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  capabilities: readonly string[];
  jobTitles: readonly CorporateJobTitleView[];
  /** Null when the member.list capability is absent — assignment UI hides. */
  members: readonly CorporateMember[] | null;
};

type FormState = { name: string; description: string };

const EMPTY_FORM: FormState = { name: "", description: "" };

function employeeName(member: CorporateMember) {
  return member.display_name ?? member.account_id;
}

// eslint-disable-next-line max-lines-per-function, complexity
export function CorporateJobTitles({
  csrfToken,
  organizationId,
  authorizationRevision,
  capabilities,
  jobTitles,
  members,
}: Props) {
  const t = useTranslations("corporate");
  const tp = useTranslations("people");
  const router = useRouter();
  const filters = usePeopleFilters();
  const [busy, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [memberQuery, setMemberQuery] = useState("");
  const [dialog, setDialog] = useState<
    | { kind: "create" }
    | { kind: "edit"; title: CorporateJobTitleView }
    | { kind: "delete"; title: CorporateJobTitleView }
    | { kind: "assign"; title: CorporateJobTitleView }
    | null
  >(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [assignSelection, setAssignSelection] = useState<string[]>([]);

  const can = (permission: string) => capabilities.includes(permission);
  const canWrite = can("job_title.update");
  const canAssign = canWrite && can("member.update") && members !== null;

  const linked = useMemo(() => {
    const map = new Map<string, CorporateMember[]>();
    for (const title of jobTitles) map.set(title.job_title_id, []);
    for (const member of members ?? []) {
      if (member.job_title_id && map.has(member.job_title_id))
        map.get(member.job_title_id)?.push(member);
    }
    return map;
  }, [jobTitles, members]);

  const stateFilter = filters.get("state");
  const query = filters.get("query").trim().toLowerCase();
  const filtered = jobTitles.filter(
    (title) =>
      (!stateFilter || title.state === stateFilter) &&
      (!query ||
        [title.name, title.description].some((value) => value.toLowerCase().includes(query))),
  );
  const page = Math.min(
    Math.max(1, Number(filters.get("page")) || 1),
    Math.max(1, Math.ceil(filtered.length / 10)),
  );
  const rows = filtered.slice((page - 1) * 10, page * 10);
  const selected = jobTitles.find((title) => title.job_title_id === selectedId) ?? null;
  const assigned = selected ? (linked.get(selected.job_title_id) ?? []) : [];
  const visibleAssigned = assigned.filter((member) =>
    [employeeName(member), member.contact_email ?? "", member.role].some((value) =>
      value.toLowerCase().includes(memberQuery.trim().toLowerCase()),
    ),
  );

  function mutate(
    path: string,
    method: "POST" | "PATCH",
    body: unknown,
    done?: (data: unknown) => void,
  ) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutation({
        csrfToken,
        organizationId,
        path,
        method,
        body,
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      setMessage(t("saved"));
      setDialog(null);
      done?.(result.data);
      router.refresh();
    });
  }

  function saveTitle(title: CorporateJobTitleView | null) {
    const isNew = title === null;
    mutate(
      `/v1/corporate/organizations/${organizationId}/job-titles${isNew ? "" : `/${title.job_title_id}`}`,
      isNew ? "POST" : "PATCH",
      {
        schema_version: 1,
        name: form.name,
        description: form.description,
        ...(isNew ? {} : { state: title.state, expected_revision: title.revision }),
        authorization_revision: authorizationRevision,
        idempotency_key: crypto.randomUUID(),
      },
      // Select the created title so the panel shows it instead of falling
      // back to the first row — otherwise a create looks like a no-op.
      (data) => {
        if (isNew) {
          const id = (data as { job_title_id?: string } | undefined)?.job_title_id;
          if (id) setSelectedId(id);
        }
      },
    );
  }

  function setTitleState(title: CorporateJobTitleView, state: "current" | "retired") {
    mutate(
      `/v1/corporate/organizations/${organizationId}/job-titles/${title.job_title_id}`,
      "PATCH",
      {
        schema_version: 1,
        name: title.name,
        description: title.description,
        state,
        expected_revision: title.revision,
        authorization_revision: authorizationRevision,
        idempotency_key: crypto.randomUUID(),
      },
    );
  }

  function setMemberTitle(member: CorporateMember, jobTitleId: string | null) {
    mutate(`/v1/corporate/organizations/${organizationId}/members/${member.account_id}`, "PATCH", {
      schema_version: 1,
      role: member.role,
      state: member.state,
      job_title_id: jobTitleId,
      expected_revision: member.revision,
      authorization_revision: authorizationRevision,
      idempotency_key: crypto.randomUUID(),
    });
  }

  return (
    <div className="min-w-0 space-y-6">
      <section className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <PeopleSearch
            label={t("searchJobTitles")}
            value={filters.get("query")}
            onChange={(value) => {
              filters.update("query", value);
            }}
          />
          <PeopleSelect
            label={t("allJobTitles")}
            value={stateFilter}
            onChange={(value) => {
              filters.update("state", value);
            }}
            options={[
              { value: "current", label: t("jobTitleCurrent") },
              { value: "retired", label: t("jobTitleRetired") },
            ]}
          />
          {can("job_title.create") ? (
            <Button
              type="button"
              className="ml-auto h-11"
              onClick={() => {
                setForm(EMPTY_FORM);
                setDialog({ kind: "create" });
              }}
            >
              <Icon name="plus" size="sm" />
              {t("createJobTitle")}
            </Button>
          ) : null}
        </div>
        <PeopleTable label={t("jobTitles")} minWidth="min-w-[640px]" framed>
          <thead>
            <tr className="border-border border-b">
              <th scope="col" className={peopleHeadClass}>
                {t("jobTitleName")}
              </th>
              <th scope="col" className={peopleHeadClass}>
                {t("description")}
              </th>
              <th scope="col" className={peopleHeadClass}>
                {t("linkedEmployees")}
              </th>
              <th scope="col" className={`${peopleHeadClass} w-11`}>
                <span className="sr-only">{t("actions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((title) => (
              <tr
                key={title.job_title_id}
                data-selected={selected?.job_title_id === title.job_title_id || undefined}
                className="border-border hover:bg-muted/30 data-[selected]:bg-primary/5 cursor-pointer border-b transition-colors last:border-0"
                onClick={() => {
                  setSelectedId(title.job_title_id);
                  setMemberQuery("");
                }}
              >
                <td className={`${peopleCellClass} font-medium whitespace-nowrap`}>
                  <span className="inline-flex items-center gap-2">
                    {title.name}
                    {title.state === "retired" ? (
                      <Badge variant="secondary">{t("jobTitleRetired")}</Badge>
                    ) : null}
                  </span>
                </td>
                <td className={`${peopleCellClass} text-muted-foreground max-w-80`}>
                  <span className="line-clamp-2">{title.description}</span>
                </td>
                <td className={`${peopleCellClass} tabular-nums`}>
                  {members === null ? "—" : (linked.get(title.job_title_id)?.length ?? 0)}
                </td>
                <td
                  className="text-right"
                  onClick={(event) => {
                    event.stopPropagation();
                  }}
                >
                  <CatalogChoiceMenu
                    icon="moreVertical"
                    variant="ghost"
                    align="end"
                    label={t("jobTitleActions", { name: title.name })}
                    options={[
                      {
                        label: t("edit"),
                        icon: "edit",
                        onSelect: () => {
                          setForm({ name: title.name, description: title.description });
                          setDialog({ kind: "edit", title });
                        },
                        disabled: !canWrite,
                      },
                      {
                        label: t("assignEmployees"),
                        icon: "team",
                        onSelect: () => {
                          setAssignSelection(
                            (linked.get(title.job_title_id) ?? []).map(
                              (member) => member.account_id,
                            ),
                          );
                          setDialog({ kind: "assign", title });
                        },
                        disabled: !canAssign,
                      },
                      title.state === "current"
                        ? {
                            label: t("delete"),
                            icon: "close",
                            separatorBefore: true,
                            onSelect: () => {
                              setDialog({ kind: "delete", title });
                            },
                            disabled: !canWrite,
                          }
                        : {
                            label: t("restoreJobTitle"),
                            icon: "check",
                            separatorBefore: true,
                            onSelect: () => {
                              setTitleState(title, "current");
                            },
                            disabled: !canWrite,
                          },
                    ]}
                  />
                </td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={4} className="text-muted-foreground py-14 text-center text-sm">
                  {t(jobTitles.length ? "noMatches" : "jobTitleNoItems")}
                </td>
              </tr>
            ) : null}
          </tbody>
        </PeopleTable>
        <PeoplePager
          total={filtered.length}
          page={page}
          kind="members"
          onPage={(value) => {
            filters.update("page", String(value));
          }}
        />
      </section>

      <CorporateDetailDrawer
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null);
        }}
        title={selected?.name ?? ""}
        description={selected?.state === "retired" ? t("jobTitleRetired") : undefined}
        actions={
          selected && canWrite ? (
            <>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={t("edit")}
                onClick={() => {
                  setForm({ name: selected.name, description: selected.description });
                  setDialog({ kind: "edit", title: selected });
                }}
              >
                <Icon name="edit" size="sm" />
              </Button>
              {selected.state === "current" ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={t("delete")}
                  className="text-destructive"
                  onClick={() => {
                    setDialog({ kind: "delete", title: selected });
                  }}
                >
                  <Icon name="close" size="sm" />
                </Button>
              ) : null}
            </>
          ) : undefined
        }
      >
        {selected ? (
          <div className="space-y-5">
            <div className="space-y-1">
              <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
                {t("description")}
              </h3>
              <p className="text-sm break-words">{selected.description || "—"}</p>
            </div>
            <div className="border-border text-muted-foreground flex items-center gap-2 rounded-sm border px-3 py-2 text-sm">
              <Icon name="user" size="sm" />
              {t("linkedEmployeesCount", { count: assigned.length })}
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-medium">{t("assignedEmployees")}</h3>
                {canAssign ? (
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => {
                      setAssignSelection(assigned.map((member) => member.account_id));
                      setDialog({ kind: "assign", title: selected });
                    }}
                  >
                    <Icon name="plus" size="sm" />
                    {t("assignEmployees")}
                  </Button>
                ) : null}
              </div>
              {assigned.length ? (
                <>
                  <Input
                    type="search"
                    value={memberQuery}
                    aria-label={t("searchEmployees")}
                    placeholder={t("searchEmployees")}
                    onChange={(event) => {
                      setMemberQuery(event.target.value);
                    }}
                  />
                  <ul className="divide-border divide-y">
                    {visibleAssigned.map((member) => (
                      <li key={member.account_id} className="flex items-center gap-2 py-2">
                        <Link
                          href={`/corporate/employees/${encodeURIComponent(member.account_id)}`}
                          className="focus-visible:ring-ring min-w-0 flex-1 rounded-sm focus-visible:ring-2 focus-visible:outline-none"
                        >
                          <PersonIdentity
                            name={employeeName(member)}
                            email={member.contact_email ?? undefined}
                          />
                        </Link>
                        {canAssign ? (
                          <CatalogChoiceMenu
                            icon="moreVertical"
                            variant="ghost"
                            align="end"
                            label={tp("personActions", { name: employeeName(member) })}
                            options={[
                              {
                                label: tp("viewProfile"),
                                icon: "user",
                                href: `/corporate/employees/${encodeURIComponent(member.account_id)}`,
                              },
                              {
                                label: t("removeAssignment"),
                                icon: "close",
                                onSelect: () => {
                                  setMemberTitle(member, null);
                                },
                              },
                            ]}
                          />
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {members !== null ? (
                <Button type="button" variant="outline" className="w-full" asChild>
                  <Link
                    href={`/corporate/employees?job_title_ids=${encodeURIComponent(selected.job_title_id)}`}
                  >
                    {t("viewAllEmployees", { count: assigned.length })}
                    <Icon name="link" size="sm" />
                  </Link>
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}
      </CorporateDetailDrawer>

      <FormDialog
        open={dialog?.kind === "create" || dialog?.kind === "edit"}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
        title={dialog?.kind === "edit" ? t("editJobTitle") : t("createJobTitle")}
        description={t("jobTitlesDescription")}
        closeLabel={t("close")}
        cancelLabel={t("cancel")}
        submitLabel={t("save")}
        busyLabel={t("saving")}
        busy={busy}
        onSubmit={() => {
          saveTitle(dialog?.kind === "edit" ? dialog.title : null);
        }}
      >
        <div className="space-y-2">
          <Label htmlFor="job-title-form-name">{t("jobTitleName")}</Label>
          <Input
            id="job-title-form-name"
            required
            value={form.name}
            onChange={(event) => {
              setForm({ ...form, name: event.target.value });
            }}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="job-title-form-description">{t("jobTitleDescription")}</Label>
          <Textarea
            id="job-title-form-description"
            value={form.description}
            onChange={(event) => {
              setForm({ ...form, description: event.target.value });
            }}
          />
        </div>
      </FormDialog>

      <FormDialog
        open={dialog?.kind === "delete"}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
        title={t("deleteJobTitle")}
        description={t("deleteJobTitleConfirm", {
          name: dialog?.kind === "delete" ? dialog.title.name : "",
        })}
        closeLabel={t("close")}
        cancelLabel={t("cancel")}
        submitLabel={t("delete")}
        submitVariant="destructive"
        busy={busy}
        onSubmit={() => {
          if (dialog?.kind === "delete") setTitleState(dialog.title, "retired");
        }}
      />

      <FormDialog
        open={dialog?.kind === "assign"}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
        title={t("assignEmployees")}
        description={dialog?.kind === "assign" ? dialog.title.name : undefined}
        closeLabel={t("close")}
        cancelLabel={t("cancel")}
        submitLabel={t("save")}
        busyLabel={t("saving")}
        busy={busy}
        onSubmit={() => {
          if (dialog?.kind !== "assign" || !members) return;
          const before = new Set(
            members
              .filter((member) => member.job_title_id === dialog.title.job_title_id)
              .map((member) => member.account_id),
          );
          const after = new Set(assignSelection);
          const changed = members.filter(
            (member) => before.has(member.account_id) !== after.has(member.account_id),
          );
          setMessage(null);
          startTransition(async () => {
            let failed = 0;
            for (const member of changed) {
              const result = await corporateMutation({
                csrfToken,
                organizationId,
                path: `/v1/corporate/organizations/${organizationId}/members/${member.account_id}`,
                method: "PATCH",
                body: {
                  schema_version: 1,
                  role: member.role,
                  state: member.state,
                  job_title_id: after.has(member.account_id) ? dialog.title.job_title_id : null,
                  expected_revision: member.revision,
                  authorization_revision: authorizationRevision,
                  idempotency_key: crypto.randomUUID(),
                },
              });
              if (!result.ok) failed += 1;
            }
            setMessage(failed ? t("assignPartial", { count: failed }) : t("saved"));
            if (!failed) setDialog(null);
            router.refresh();
          });
        }}
      >
        <SearchableMultiSelect
          name="members"
          label={t("assignedEmployees")}
          searchLabel={t("searchEmployees")}
          options={(members ?? []).map((member) => ({
            value: member.account_id,
            label: member.contact_email
              ? `${employeeName(member)} · ${member.contact_email}`
              : employeeName(member),
          }))}
          selected={assignSelection}
          onChange={setAssignSelection}
          modal
          inline
          closeLabel={t("close")}
          selectionSuffix={t("selectedSuffix")}
          emptyHint={t("searchEmployees")}
        />
      </FormDialog>

      {message ? (
        <p className="text-muted-foreground text-sm" role="status" aria-live="polite">
          {message}
        </p>
      ) : null}
    </div>
  );
}
