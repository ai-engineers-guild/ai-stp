"use client";

import { Fragment, useEffect, useState, useTransition, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { queryEntityActionMenu } from "@/lib/entity-action-query";
import { MenuItem, MenuSeparator } from "@/components/atoms/menu";
import { CorporateResourceDeleteMenuItem } from "@/components/organisms/corporate-resource-actions";
import type { EntityActionMenu, EntityActionSubject } from "@/lib/api/generated/types.gen";
import { registryShow } from "@/lib/cli-copy";
import { Link } from "@/lib/i18n/navigation";
import { Icon } from "@/theme";
import { deleteObjectAction } from "@/actions/object-presentation";
import { ContactReportDialog } from "@/components/organisms/contact-report-dialog";
import { toast } from "sonner";
import { corporateMutation } from "@/lib/api/corporate-mutation";

type MenuResult = { menu: EntityActionMenu; csrfToken: string };
/** Prefetch while the card is visible; each host owns and discards its projection. */
export function usePreloadedEntityMenu(subject: EntityActionSubject | null) {
  const key = JSON.stringify(subject);
  const [loaded, setLoaded] = useState<{ key: string; result: MenuResult } | null>(null);
  useEffect(() => {
    if (key === "null") return;
    let current = true;
    void queryEntityActionMenu(JSON.parse(key) as EntityActionSubject)
      .then((result) => {
        if (current) setLoaded({ key, result });
      })
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [key]);
  return loaded && loaded.key === key ? loaded.result : null;
}

/** The server selects actions and groups. Entries supply behavior, never authority or order. */
export function EntityActionItems(props: {
  subject: EntityActionSubject;
  entries: Record<string, ReactNode>;
  onLoaded?: (menu: EntityActionMenu, csrfToken: string) => void;
  initialResult?: MenuResult | null;
}) {
  return <LoadedEntityActionItems key={JSON.stringify(props.subject)} {...props} />;
}

function LoadedEntityActionItems({
  subject,
  entries,
  onLoaded,
  initialResult,
}: {
  subject: EntityActionSubject;
  entries: Record<string, ReactNode>;
  onLoaded?: (menu: EntityActionMenu, csrfToken: string) => void;
  initialResult?: MenuResult | null;
}) {
  const common = useTranslations("common");
  const hub = useTranslations("hub");
  const [result, setResult] = useState<MenuResult | null>(initialResult ?? null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [reportOpen, setReportOpen] = useState(false);
  const key = JSON.stringify(subject);
  useEffect(() => {
    let current = true;
    void queryEntityActionMenu(JSON.parse(key) as EntityActionSubject)
      .then(({ menu, csrfToken }) => {
        if (current) {
          setFailed(false);
          setResult({ menu, csrfToken });
          onLoaded?.(menu, csrfToken);
        }
      })
      .catch(() => {
        if (current) {
          setResult(null);
          setFailed(true);
        }
      });
    return () => {
      current = false;
    };
    // The subject controls loading; callbacks describe the current host only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt]);
  if (failed)
    return (
      <MenuItem
        onSelect={(event) => {
          event.preventDefault();
          setResult(null);
          setFailed(false);
          setAttempt(attempt + 1);
        }}
      >
        {common("requestFailed")} {common("retry")}
      </MenuItem>
    );
  if (!result) return <MenuItem disabled>{common("loading")}</MenuItem>;
  const { menu, csrfToken } = result;
  return (
    <>
      {menu.actions.map((action, index) => {
        const entry = entries[action.id] ?? (
          <DefaultEntityAction
            id={action.id}
            menu={menu}
            csrfToken={csrfToken}
            onReport={() => {
              setReportOpen(true);
            }}
          />
        );
        return (
          <Fragment key={action.id}>
            {index > 0 && menu.actions[index - 1]?.group !== action.group ? (
              <MenuSeparator />
            ) : null}
            {entry}
          </Fragment>
        );
      })}
      <ContactReportDialog
        kind="entity"
        target={`corporate:${subject.kind}:${subject.id}`}
        label={hub("report")}
        open={reportOpen}
        onOpenChange={setReportOpen}
        hideTrigger
      />
    </>
  );
}

function editHref(menu: EntityActionMenu, id: string, catalogObject: boolean) {
  const subject = menu.subject;
  return catalogObject
    ? `/objects/${subject.kind}/${subject.id}/edit`
    : subject.kind === "category"
      ? `/corporate/admin/tech-categories?entity=${subject.id}&action=edit`
      : subject.kind === "area"
        ? `/corporate/admin/technology-areas?entity=${subject.id}&action=edit`
        : subject.kind === "job_title"
          ? `/corporate/admin/job-titles?entity=${subject.id}&action=edit`
          : subject.kind === "role"
            ? `/corporate/admin/roles?entity=${encodeURIComponent(subject.id)}&action=edit`
            : `${menu.href}/${id === "edit_presentation" && ["member", "team", "project"].includes(subject.kind) ? "presentation/edit" : "edit"}`;
}

function DefaultEntityAction({
  id,
  menu,
  csrfToken,
  onReport,
}: {
  id: string;
  menu: EntityActionMenu;
  csrfToken: string;
  onReport: () => void;
}) {
  const subject = menu.subject;
  const common = useTranslations("common");
  const catalog = useTranslations("catalog");
  const objects = useTranslations("objects");
  const hub = useTranslations("hub");
  const locale = useLocale();
  const [deleting, startDelete] = useTransition();
  const catalogObject = subject.kind === "component" || subject.kind === "setup";
  if (id === "copy_id" || id === "copy_url" || (id === "copy_cli" && catalogObject))
    return (
      <MenuItem
        onSelect={() => {
          const value =
            id === "copy_cli"
              ? registryShow(subject.kind as "component" | "setup", subject.id)
              : id === "copy_id"
                ? subject.id
                : new URL(menu.href ?? window.location.pathname, window.location.origin).toString();
          void navigator.clipboard
            .writeText(value)
            .then(() => toast.success(catalog("copied")))
            .catch(() => toast.error(common("requestFailed")));
        }}
      >
        <Icon name="copy" size="sm" />
        {catalog(id === "copy_id" ? "copyId" : id === "copy_cli" ? "copyCli" : "copyUrl")}
      </MenuItem>
    );
  if (id === "share")
    return (
      <MenuItem
        onSelect={() => {
          const url = new URL(
            menu.href ?? window.location.pathname,
            window.location.origin,
          ).toString();
          void navigator.clipboard
            .writeText(url)
            .then(() => toast.success(catalog("copied")))
            .catch(() => toast.error(common("requestFailed")));
        }}
      >
        <Icon name="link" size="sm" />
        {catalog("share")}
      </MenuItem>
    );
  if (id === "report")
    return (
      <MenuItem
        onSelect={(event) => {
          event.preventDefault();
          onReport();
        }}
      >
        <Icon name="flag" size="sm" />
        {hub("report")}
      </MenuItem>
    );
  if (id === "open" && menu.href)
    return (
      <MenuItem asChild>
        <Link href={menu.href}>
          <Icon name="eye" size="sm" />
          {hub("openDetails")}
        </Link>
      </MenuItem>
    );
  if ((id === "edit" || id === "edit_presentation") && menu.href) {
    const href = editHref(menu, id, catalogObject);
    return (
      <MenuItem asChild>
        <Link href={href}>
          <Icon name="edit" size="sm" />
          {id === "edit_presentation" ? objects("editPresentation") : hub("edit")}
        </Link>
      </MenuItem>
    );
  }
  if (id === "manage_access")
    return (
      <MenuItem asChild>
        <Link
          href={
            catalogObject
              ? `/access?object_kind=${subject.kind}&stable_id=${encodeURIComponent(subject.id)}`
              : `/corporate/employees/${encodeURIComponent(subject.id)}/access`
          }
        >
          <Icon name="access" size="sm" />
          {objects("manageAccess")}
        </Link>
      </MenuItem>
    );
  if (id === "delete" && catalogObject)
    return (
      <MenuItem
        className="text-destructive"
        disabled={deleting}
        onSelect={(event) => {
          event.preventDefault();
          if (!window.confirm(catalog("objectDeleteConfirm"))) return;
          startDelete(async () => {
            try {
              const value = await deleteObjectAction({
                csrfToken,
                stableId: subject.id,
                objectKind: subject.kind as "component" | "setup",
                locale,
              });
              if (value.ok) window.location.assign(`/${locale}/catalog`);
              else toast.error(value.message);
            } catch {
              toast.error(common("requestFailed"));
            }
          });
        }}
      >
        <Icon name="close" size="sm" />
        {catalog("objectDelete")}
      </MenuItem>
    );
  return <CorporateMenuAction id={id} menu={menu} csrfToken={csrfToken} />;
}

function CorporateMenuAction({
  id,
  menu,
  csrfToken,
}: {
  id: string;
  menu: EntityActionMenu;
  csrfToken: string;
}) {
  const subject = menu.subject;
  const corporate = useTranslations("corporate");
  const technology = useTranslations("technology");
  const people = useTranslations("people");
  const common = useTranslations("common");
  const [busy, start] = useTransition();
  if (
    (subject.kind === "job_title" && ["retire", "restore"].includes(id)) ||
    (subject.kind === "role" && id === "delete")
  )
    return (
      <MenuItem asChild>
        <Link
          href={`/corporate/admin/${subject.kind === "role" ? "roles" : "job-titles"}?entity=${encodeURIComponent(subject.id)}&action=${id}`}
        >
          {id === "restore" ? corporate("restoreJobTitle") : corporate("delete")}
        </Link>
      </MenuItem>
    );
  if (
    (id === "restore" || id === "retire") &&
    subject.organization_id &&
    menu.revision !== null &&
    menu.authorization_revision !== null
  ) {
    const jobTitle = subject.kind === "job_title";
    const resource = jobTitle
      ? "job-titles"
      : subject.kind === "area"
        ? "technology-areas"
        : "technology-categories";
    return (
      <MenuItem
        disabled={busy}
        onSelect={(event) => {
          event.preventDefault();
          start(async () => {
            try {
              const result = await corporateMutation({
                csrfToken,
                organizationId: subject.organization_id ?? "",
                path: `/v1/corporate/organizations/${subject.organization_id}/${resource}/${subject.id}${jobTitle ? "" : "/lifecycle"}`,
                method: jobTitle ? "PATCH" : "POST",
                body: {
                  schema_version: 1,
                  expected_revision: menu.revision,
                  authorization_revision: menu.authorization_revision,
                  idempotency_key: crypto.randomUUID(),
                  ...(jobTitle
                    ? { state: id === "retire" ? "retired" : "current" }
                    : { target: "active" }),
                },
              });
              if (result.ok) window.location.reload();
              else toast.error(result.message);
            } catch {
              toast.error(common("requestFailed"));
            }
          });
        }}
      >
        {id === "restore" ? technology("restore") : corporate("jobTitleRetired")}
      </MenuItem>
    );
  }
  if (["assign_members", "duplicate", "manage_technologies"].includes(id)) {
    const href =
      subject.kind === "role"
        ? "/corporate/admin/roles"
        : subject.kind === "job_title"
          ? "/corporate/admin/job-titles"
          : "/corporate/admin/tech-categories";
    const label =
      id === "manage_technologies"
        ? technology("manageTechnologies")
        : id === "duplicate"
          ? common("copy")
          : people("manageAccess");
    return (
      <MenuItem asChild>
        <Link href={`${href}?entity=${encodeURIComponent(subject.id)}&action=${id}`}>{label}</Link>
      </MenuItem>
    );
  }
  const resources: Partial<Record<EntityActionSubject["kind"], string>> = {
    team: "teams",
    member: "members",
    project: "projects",
    technology: "technologies",
    role: "roles",
    category: "technology-categories",
    area: "technology-areas",
    scan: "technology-scans",
  };
  const resource = resources[subject.kind];
  if (
    id === "delete" &&
    resource &&
    menu.subject.organization_id &&
    menu.revision !== null &&
    menu.authorization_revision !== null
  )
    return (
      <CorporateResourceDeleteMenuItem
        csrfToken={csrfToken}
        organizationId={menu.subject.organization_id}
        authorizationRevision={menu.authorization_revision}
        revision={menu.revision}
        resource={
          resource as
            | "teams"
            | "members"
            | "projects"
            | "technologies"
            | "roles"
            | "technology-categories"
            | "technology-scans"
            | "technology-areas"
        }
        resourceId={subject.id}
        label={corporate("delete")}
        confirmLabel={corporate("confirmDelete")}
      />
    );
  return null;
}
