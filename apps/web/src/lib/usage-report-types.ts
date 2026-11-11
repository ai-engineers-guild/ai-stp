type UsageGroupBy =
  | "component"
  | "setup"
  | "employee"
  | "device"
  | "project"
  | "harness"
  | "outcome";

type UsageReportRow = {
  group_value: string;
  component_kind: string | null;
  component_stable_id: string | null;
  component_version: string | null;
  setup_stable_id: string | null;
  setup_version: string | null;
  invocations: number;
  succeeded: number;
  failed: number;
  cancelled: number;
  employees: number;
  devices: number;
  first_invoked_at: string;
  last_invoked_at: string;
};

type UsageAssignedRow = {
  object_kind: "setup" | "component";
  stable_id: string;
  version: string | null;
  state: "recorded_use" | "no_recorded_use";
  invocations: number;
  last_invoked_at: string | null;
};

export type UsageReport = {
  schema_version: 1;
  organization_id: string;
  generated_at: string;
  invoked_from: string | null;
  invoked_to: string | null;
  group_by: UsageGroupBy;
  total_events: number;
  rows: UsageReportRow[];
  assigned: UsageAssignedRow[];
};
