import { Badge } from "@/components/atoms/badge";
import { cn } from "@/lib/cn";

import type { InstallationHeartbeat, InstallationHealthState } from "./types";

const HEALTH_VARIANT: Record<
  InstallationHealthState,
  "success" | "warning" | "destructive" | "secondary" | "outline"
> = {
  active: "success",
  stale: "warning",
  failing: "destructive",
  disabled: "secondary",
  unknown: "outline",
};

/** One row per installation: account, device, CLI version, reported health. */
export function InstallationsTable({
  items,
  labels,
  className,
}: {
  items: InstallationHeartbeat[];
  labels: {
    account: string;
    device: string;
    cli: string;
    lastSync: string;
    health: string;
    never: string;
  };
  className?: string;
}) {
  return (
    <table className={cn("w-full text-sm", className)}>
      <thead>
        <tr className="text-muted-foreground border-b text-left">
          <th className="py-2 pr-4 font-medium">{labels.account}</th>
          <th className="py-2 pr-4 font-medium">{labels.device}</th>
          <th className="py-2 pr-4 font-medium">{labels.cli}</th>
          <th className="py-2 pr-4 font-medium">{labels.lastSync}</th>
          <th className="py-2 font-medium">{labels.health}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.device_id} className="border-b last:border-0">
            <td className="py-2 pr-4 font-mono text-xs">{item.account_id}</td>
            <td className="py-2 pr-4 font-mono text-xs">{item.device_id}</td>
            <td className="py-2 pr-4">{item.cli_version}</td>
            <td className="text-muted-foreground py-2 pr-4">{item.last_sync_at ?? labels.never}</td>
            <td className="py-2">
              <Badge variant={HEALTH_VARIANT[item.health_state]}>{item.health_state}</Badge>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
