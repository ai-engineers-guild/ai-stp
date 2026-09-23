/**
 * Local mirrors of the installation-heartbeat wire contracts (#215). The
 * generated client picks these up when contract export wiring lands; until
 * then the shape here is the source the BFF route and page share.
 */

export type InstallationHealthState = "active" | "stale" | "failing" | "disabled" | "unknown";

export interface InstallationHeartbeat {
  schema_version: 1;
  organization_id: string;
  account_id: string;
  device_id: string;
  cli_version: string;
  capabilities: string[];
  last_sync_at: string | null;
  reported_state: "active" | "failing" | "disabled";
  health_state: InstallationHealthState;
  checked_at: string;
  received_at: string;
  revision: number;
  stale_after_seconds: number;
}

export interface InstallationHeartbeatList {
  schema_version: 1;
  organization_id: string;
  evaluated_at: string;
  stale_after_seconds: number;
  total: number;
  items: InstallationHeartbeat[];
}
