"use client";
import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { SearchableMultiSelect } from "@/components/molecules/searchable-multi-select";
import { Link, useRouter } from "@/lib/i18n/navigation";

export function CorporateProjectMemberships({
  organizationId,
  authorizationRevision,
  csrfToken,
  projectId,
  accountId,
  options,
  assigned,
  canManage,
}: {
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  projectId?: string;
  accountId?: string;
  options: { id: string; name: string }[];
  assigned: { id: string; name: string }[];
  canManage: boolean;
}) {
  const h = useTranslations("hub");
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const retry = useRef<{ effect: string; key: string } | null>(null);
  const employees = projectId !== undefined;
  async function change(id: string, operation: "assign" | "remove") {
    if (!canManage || !id) return;
    const effect = { account_id: accountId ?? id, project_id: projectId ?? id, operation };
    const fingerprint = JSON.stringify(effect);
    if (retry.current?.effect !== fingerprint)
      retry.current = { effect: fingerprint, key: crypto.randomUUID() };
    setBusy(true);
    setMessage(null);
    try {
      const result = await corporateMutationAction({
        organizationId,
        csrfToken,
        path: `/v1/corporate/organizations/${organizationId}/membership-assignments`,
        method: "POST",
        body: {
          ...effect,
          schema_version: 1,
          authorization_revision: authorizationRevision,
          idempotency_key: retry.current.key,
        },
      });
      if (!result.ok) {
        setMessage(result.message);
        return;
      }
      retry.current = null;
      setAdding(false);
      setSelected([]);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-medium">{h(employees ? "employees" : "projects")}</h2>
      <ul className="divide-border divide-y">
        {assigned.map((item) => (
          <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <Link
              href={`/corporate/${employees ? "employees" : "projects"}/${item.id}`}
              className="inline-flex min-h-11 items-center underline underline-offset-4"
            >
              {item.name}
            </Link>
            {canManage && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  void change(item.id, "remove");
                }}
              >
                {h("unlink")}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {!assigned.length && <p className="text-muted-foreground text-sm">{h("empty")}</p>}
      {canManage && (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => {
            setAdding(!adding);
          }}
        >
          {h(adding ? "cancel" : "addMembership")}
        </Button>
      )}
      {adding && (
        <form
          className="max-w-xl space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            void change(selected[0] ?? "", "assign");
          }}
        >
          <fieldset disabled={busy} className="space-y-3">
            <SearchableMultiSelect
              name="membership"
              label={h(employees ? "employees" : "projects")}
              searchLabel={h("search")}
              options={options
                .filter((item) => !assigned.some((value) => value.id === item.id))
                .map((item) => ({ value: item.id, label: item.name }))}
              selected={selected}
              multiple={false}
              onChange={setSelected}
              closeLabel={h("cancel")}
            />
            <Button type="submit" disabled={!selected.length}>
              {h("save")}
            </Button>
          </fieldset>
        </form>
      )}
      {message && (
        <p role="alert" className="text-sm">
          {message}
        </p>
      )}
    </section>
  );
}
