"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/atoms/badge";
import { Button } from "@/components/atoms/button";
import { StatePanel } from "@/components/molecules/state-panel";

import type { UsageGroupBy, UsageReport } from "./usage-report-types";

const GROUPS: readonly UsageGroupBy[] = [
  "component",
  "setup",
  "employee",
  "device",
  "project",
  "harness",
  "outcome",
];

type Props = {
  labels: {
    title: string;
    groupBy: string;
    invocations: string;
    employees: string;
    devices: string;
    outcomes: string;
    firstUsed: string;
    lastUsed: string;
    assignedTitle: string;
    assignedObject: string;
    assignedState: string;
    recordedUse: string;
    noRecordedUse: string;
    loading: string;
    empty: string;
    failed: string;
    retry: string;
  };
};

export function UsageReportPanel({ labels }: Props) {
  const [groupBy, setGroupBy] = useState<UsageGroupBy>("component");
  const [reloadKey, setReloadKey] = useState(0);
  const [report, setReport] = useState<UsageReport | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/corporate/usage?group_by=${groupBy}`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status));
        return (await response.json()) as UsageReport;
      })
      .then((data) => {
        if (cancelled) return;
        setReport(data);
        setState("ready");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [groupBy, reloadKey]);

  if (state === "error") {
    return (
      <StatePanel
        kind="error"
        title={labels.failed}
        action={
          <Button
            type="button"
            onClick={() => {
              setState("loading");
              setReloadKey((value) => value + 1);
            }}
          >
            {labels.retry}
          </Button>
        }
      />
    );
  }
  if (state === "loading") {
    return <StatePanel kind="loading" title={labels.loading} />;
  }
  if (!report || report.rows.length === 0) {
    return <StatePanel kind="empty" title={labels.empty} />;
  }

  return (
    <section aria-label={labels.title}>
      <div>
        <label htmlFor="usage-group-by">{labels.groupBy}</label>
        <select
          id="usage-group-by"
          value={groupBy}
          onChange={(event) => {
            setState("loading");
            setGroupBy(event.target.value as UsageGroupBy);
          }}
        >
          {GROUPS.map((group) => (
            <option key={group} value={group}>
              {group}
            </option>
          ))}
        </select>
      </div>
      <table>
        <thead>
          <tr>
            <th scope="col">{labels.groupBy}</th>
            <th scope="col">{labels.invocations}</th>
            <th scope="col">{labels.outcomes}</th>
            <th scope="col">{labels.employees}</th>
            <th scope="col">{labels.devices}</th>
            <th scope="col">{labels.firstUsed}</th>
            <th scope="col">{labels.lastUsed}</th>
          </tr>
        </thead>
        <tbody>
          {report.rows.map((row) => (
            <tr key={row.group_value}>
              <td>{row.group_value}</td>
              <td>{row.invocations}</td>
              <td>
                {row.succeeded}/{row.failed}/{row.cancelled}
              </td>
              <td>{row.employees}</td>
              <td>{row.devices}</td>
              <td>{row.first_invoked_at}</td>
              <td>{row.last_invoked_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {report.assigned.length > 0 && (
        <table aria-label={labels.assignedTitle}>
          <thead>
            <tr>
              <th scope="col">{labels.assignedObject}</th>
              <th scope="col">{labels.assignedState}</th>
              <th scope="col">{labels.invocations}</th>
              <th scope="col">{labels.lastUsed}</th>
            </tr>
          </thead>
          <tbody>
            {report.assigned.map((row) => (
              <tr key={`${row.object_kind}:${row.stable_id}:${row.version ?? ""}`}>
                <td>
                  {row.object_kind}:{row.stable_id}
                  {row.version ? `@${row.version}` : ""}
                </td>
                <td>
                  <Badge>
                    {row.state === "recorded_use" ? labels.recordedUse : labels.noRecordedUse}
                  </Badge>
                </td>
                <td>{row.invocations}</td>
                <td>{row.last_invoked_at ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
