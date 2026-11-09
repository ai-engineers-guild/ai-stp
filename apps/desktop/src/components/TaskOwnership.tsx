import { useText } from "../i18n";
import { personalTaskOwnership } from "../contracts";

export default function TaskOwnership({
  value,
  compact = false,
}: {
  value: unknown;
  compact?: boolean;
}) {
  const msg = useText();
  const owner = personalTaskOwnership(value);
  if (!owner)
    return (
      <p className="text-xs text-muted-foreground">
        {msg("taskOwnership.taskOwnershipIsNotReportedByThisEngine")}
      </p>
    );
  return (
    <div className="space-y-1 text-xs text-muted-foreground">
      <p>{msg("taskOwnership.personalTaskRetainedLocalOwner")}</p>
      {!compact && (
        <details>
          <summary className="cursor-pointer">
            {msg("taskOwnership.originalTaskIdentity")}
          </summary>
          <dl className="mt-2 space-y-1 font-mono break-all">
            <dt>{msg("taskOwnership.localAccount")}</dt>
            <dd>{owner.native_account_id}</dd>
            <dt>{msg("taskOwnership.device")}</dt>
            <dd>{owner.native_device_id}</dd>
          </dl>
        </details>
      )}
    </div>
  );
}
