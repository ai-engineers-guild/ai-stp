"use client";

import { useState, useTransition } from "react";
import { corporateMutationAction } from "@/actions/corporate";
import { Button } from "@/components/atoms/button";
import { Link, useRouter } from "@/lib/i18n/navigation";
import type { EmployeeTechnologyList, TechnologyView } from "@/lib/api/generated/types.gen";

export function CorporateEmployeeTechnologies({
  employee,
  technologies,
  assignments,
  organizationId,
  authorizationRevision,
  csrfToken,
  canManage,
  labels,
}: {
  employee: { account_id: string };
  technologies: readonly TechnologyView[];
  assignments: EmployeeTechnologyList;
  organizationId: string;
  authorizationRevision: number;
  csrfToken: string;
  canManage: boolean;
  labels: {
    edit: string;
    empty: string;
    assign: string;
    remove: string;
    technology: string;
  };
}) {
  const router = useRouter();
  const [selected, setSelected] = useState(technologies[0]?.technology_id ?? "");
  const [busy, startTransition] = useTransition();
  if (!canManage) return null;
  function submit(state: "current" | "retired", technologyId: string, revision: number) {
    startTransition(async () => {
      const result = await corporateMutationAction({
        csrfToken,
        organizationId,
        path: "/v1/corporate/organizations/" + organizationId + "/employee-technologies",
        method: "PUT",
        body: {
          account_id: employee.account_id,
          technology_id: technologyId,
          state,
          expected_revision: revision,
          authorization_revision: authorizationRevision,
          idempotency_key: crypto.randomUUID(),
        },
      });
      if (result.ok) router.refresh();
    });
  }
  return (
    <details>
      <summary className="min-h-11 cursor-pointer py-3 text-sm underline underline-offset-4">
        {labels.edit}
      </summary>
      <div className="space-y-4 pt-3">
        {assignments.items.length ? (
          <ul className="divide-border divide-y">
            {assignments.items.map((item) => (
              <li
                key={item.relation_id}
                className="flex flex-wrap items-center justify-between gap-3 py-3"
              >
                <Link
                  href={`/corporate/technologies/${item.technology_id}`}
                  className="underline underline-offset-4"
                >
                  {technologies.find(
                    (technology) => technology.technology_id === item.technology_id,
                  )?.name ?? labels.technology}
                </Link>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    submit("retired", item.technology_id, item.revision);
                  }}
                >
                  {labels.remove}
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">{labels.empty}</p>
        )}
        <div className="flex flex-wrap items-end gap-3">
          <select
            aria-label={labels.technology}
            value={selected}
            onChange={(event) => {
              setSelected(event.target.value);
            }}
            className="border-input bg-background min-h-11 min-w-56 rounded-sm border px-3 text-sm"
          >
            {technologies.map((technology) => (
              <option key={technology.technology_id} value={technology.technology_id}>
                {technology.name}
              </option>
            ))}
          </select>
          <Button
            type="button"
            disabled={busy || !selected}
            onClick={() => {
              submit("current", selected, 0);
            }}
          >
            {labels.assign}
          </Button>
        </div>
      </div>
    </details>
  );
}
