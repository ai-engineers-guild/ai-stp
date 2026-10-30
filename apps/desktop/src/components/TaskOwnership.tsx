import { personalTaskOwnership } from "../contracts";

export default function TaskOwnership({ value, compact = false }: { value: unknown; compact?: boolean }) {
  const owner = personalTaskOwnership(value);
  if (!owner) return <p className="text-xs text-muted-foreground">Task ownership is not reported by this engine.</p>;
  return (
    <div className="space-y-1 text-xs text-muted-foreground">
      <p>Personal task · retained local owner</p>
      {!compact && <details>
        <summary className="cursor-pointer">Original task identity</summary>
        <dl className="mt-2 space-y-1 break-all font-mono">
          <dt>Local account</dt><dd>{owner.native_account_id}</dd>
          <dt>Device</dt><dd>{owner.native_device_id}</dd>
        </dl>
      </details>}
    </div>
  );
}
