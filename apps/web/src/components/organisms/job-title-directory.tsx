"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { corporateMutationAction } from "@/actions/corporate";
import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import { Label } from "@/components/atoms/label";
import { Select } from "@/components/atoms/select";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/atoms/menu";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/atoms/dialog";
import { ExpandableSearch } from "@/components/molecules/expandable-search";
import { PagePager } from "@/components/molecules/page-pager";
import { Icon } from "@/theme";
import type { CorporateJobTitleView } from "@/lib/api/generated/types.gen";

const PAGE_SIZE = 12;

type JobTitleDraft = { name: string; description: string; state: "current" | "retired" };
type MutationSave = (path: string, method: "POST" | "PATCH", body: object, done: () => void) => void;

export function JobTitleDirectory({
  csrfToken,
  organizationId,
  authorizationRevision,
  permissions,
  jobTitles,
}: {
  csrfToken: string;
  organizationId: string;
  authorizationRevision: number;
  permissions: readonly string[];
  jobTitles: readonly CorporateJobTitleView[];
}) {
  const c = useTranslations("corporate");
  const h = useTranslations("hub");
  const router = useRouter();
  const [busy, startTransition] = useTransition();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<CorporateJobTitleView | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const canCreate = permissions.includes("job_title.create");
  const canUpdate = permissions.includes("job_title.update");
  const needle = query.trim().toLocaleLowerCase();
  const filtered = jobTitles.filter(
    (item) => !needle || `${item.name} ${item.description}`.toLocaleLowerCase().includes(needle),
  );
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, totalPages);
  const shown = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);

  function save(path: string, method: "POST" | "PATCH", body: object, done: () => void) {
    setMessage(null);
    startTransition(async () => {
      const result = await corporateMutationAction({
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
      setMessage(c("saved"));
      done();
      router.refresh();
    });
  }

  return (
    <div className="min-w-0 space-y-5">
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-3">
        <ExpandableSearch
          id="job-title-search"
          value={query}
          onChange={(value) => {
            setQuery(value);
            setPage(1);
          }}
          label={h("openSearch")}
          fieldLabel={h("search")}
          placeholder={h("search")}
        />
        {canCreate && (
          <Button
            type="button"
            size="lg"
            onClick={() => {
              setCreating(true);
            }}
          >
            <span aria-hidden="true" className="text-xl leading-none">
              +
            </span>
            {c("create")}
          </Button>
        )}
      </div>
      <p className="text-muted-foreground text-sm" aria-live="polite">
        {filtered.length} {c("jobTitles")}
      </p>
      {shown.length ? (
        <ul className="grid min-w-0 gap-3 md:grid-cols-2">
          {shown.map((item) => (
            <JobTitleCard
              key={item.job_title_id}
              item={item}
              canUpdate={canUpdate}
              onEdit={setEditing}
            />
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground border-border rounded-lg border border-dashed p-8 text-center text-sm">
          {jobTitles.length ? h("noMatches") : c("jobTitleNoItems")}
        </p>
      )}
      {totalPages > 1 && (
        <PagePager
          label={h("pagination")}
          page={current}
          totalPages={totalPages}
          onPage={setPage}
          controls={{
            previous: h("previous"),
            next: h("next"),
            page: (value) => h("page", { page: value }),
          }}
        />
      )}
      {message && (
        <p role="status" className="text-muted-foreground text-sm" aria-live="polite">
          {message}
        </p>
      )}
      <JobTitleDialogs
        creating={creating}
        setCreating={setCreating}
        editing={editing}
        setEditing={setEditing}
        busy={busy}
        save={save}
        organizationId={organizationId}
        authorizationRevision={authorizationRevision}
      />
    </div>
  );
}

function JobTitleCard({
  item,
  canUpdate,
  onEdit,
}: {
  item: CorporateJobTitleView;
  canUpdate: boolean;
  onEdit: (item: CorporateJobTitleView) => void;
}) {
  const c = useTranslations("corporate");
  const h = useTranslations("hub");
  return (
    <li className="min-w-0">
      <article className="border-border bg-card relative min-w-0 overflow-hidden rounded-lg border p-4">
        <div className="flex min-w-0 items-start gap-3 pr-11">
          <span className="bg-muted border-border text-foreground inline-flex size-10 shrink-0 items-center justify-center rounded-md border">
            <Icon name="user" size="sm" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h3 className="min-w-0 text-lg leading-tight font-medium tracking-tight break-words">
                {item.name}
              </h3>
              <Badge variant={item.state === "retired" ? "secondary" : "success"}>
                {item.state === "retired" ? c("jobTitleRetired") : c("jobTitleCurrent")}
              </Badge>
            </div>
            {item.description ? (
              <p className="text-muted-foreground mt-2 text-sm leading-relaxed break-words">
                {item.description}
              </p>
            ) : null}
          </div>
        </div>
        {canUpdate && (
          <div className="absolute top-4 right-4">
            <Menu>
              <MenuTrigger asChild>
                <Button size="icon" variant="ghost" aria-label={h("moreActions")}>
                  <Icon name="more" size="sm" />
                </Button>
              </MenuTrigger>
              <MenuContent>
                <MenuItem
                  onSelect={() => {
                    onEdit(item);
                  }}
                >
                  {c("edit")}
                </MenuItem>
              </MenuContent>
            </Menu>
          </div>
        )}
      </article>
    </li>
  );
}

function jobTitleLabels(c: (key: string) => string) {
  return {
    name: c("jobTitleName"),
    description: c("jobTitleDescription"),
    state: c("jobTitleState"),
    current: c("jobTitleCurrent"),
    retired: c("jobTitleRetired"),
  };
}

function JobTitleDialogs({
  creating,
  setCreating,
  editing,
  setEditing,
  busy,
  save,
  organizationId,
  authorizationRevision,
}: {
  creating: boolean;
  setCreating: (open: boolean) => void;
  editing: CorporateJobTitleView | null;
  setEditing: (item: CorporateJobTitleView | null) => void;
  busy: boolean;
  save: MutationSave;
  organizationId: string;
  authorizationRevision: number;
}) {
  const c = useTranslations("corporate");
  const labels = jobTitleLabels(c);
  return (
    <>
      <JobTitleDialog
        open={creating}
        onOpenChange={setCreating}
        title={c("create")}
        description={c("jobTitlesDescription")}
        busy={busy}
        labels={{ ...labels, save: c("create"), saving: c("creating"), showState: false }}
        onSubmit={(draft) => {
          save(
            `/v1/corporate/organizations/${organizationId}/job-titles`,
            "POST",
            {
              schema_version: 1,
              name: draft.name,
              description: draft.description,
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            },
            () => {
              setCreating(false);
            },
          );
        }}
      />
      <JobTitleDialog
        key={editing?.job_title_id ?? "edit-none"}
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
        title={c("edit")}
        description={c("jobTitlesDescription")}
        busy={busy}
        initial={
          editing
            ? { name: editing.name, description: editing.description, state: editing.state }
            : undefined
        }
        labels={{ ...labels, save: c("jobTitleSave"), saving: c("saving"), showState: true }}
        onSubmit={(draft) => {
          if (!editing) return;
          save(
            `/v1/corporate/organizations/${organizationId}/job-titles/${editing.job_title_id}`,
            "PATCH",
            {
              schema_version: 1,
              name: draft.name,
              description: draft.description,
              state: draft.state,
              expected_revision: editing.revision,
              authorization_revision: authorizationRevision,
              idempotency_key: crypto.randomUUID(),
            },
            () => {
              setEditing(null);
            },
          );
        }}
      />
    </>
  );
}

function JobTitleDialog({
  open,
  onOpenChange,
  title,
  description,
  busy,
  initial,
  labels,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  busy: boolean;
  initial?: JobTitleDraft | undefined;
  labels: ReturnType<typeof jobTitleLabels> & {
    save: string;
    saving: string;
    showState: boolean;
  };
  onSubmit: (draft: JobTitleDraft) => void;
}) {
  const [draft, setDraft] = useState<JobTitleDraft>(
    initial ?? { name: "", description: "", state: "current" },
  );
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit(draft);
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="job-title-name">{labels.name}</Label>
            <Input
              id="job-title-name"
              required
              value={draft.name}
              onChange={(event) => {
                setDraft({ ...draft, name: event.target.value });
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="job-title-description">{labels.description}</Label>
            <Input
              id="job-title-description"
              value={draft.description}
              onChange={(event) => {
                setDraft({ ...draft, description: event.target.value });
              }}
            />
          </div>
          {labels.showState && (
            <div className="space-y-2">
              <Label htmlFor="job-title-state">{labels.state}</Label>
              <Select
                id="job-title-state"
                value={draft.state}
                onChange={(event) => {
                  setDraft({ ...draft, state: event.target.value as JobTitleDraft["state"] });
                }}
                className="border-input bg-background h-11 w-full rounded-sm border px-3 text-sm"
              >
                <option value="current">{labels.current}</option>
                <option value="retired">{labels.retired}</option>
              </Select>
            </div>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? labels.saving : labels.save}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
