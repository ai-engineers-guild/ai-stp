import type { ReactNode } from "react";
import {
  ArrowUpRight,
  CircleCheck,
  CircleAlert,
  CircleDashed,
} from "lucide-react";
import { Link } from "react-router";
import { useText, type MessageKey } from "../i18n";

const statusMessages: Record<string, MessageKey> = {
  ready: "status.ready",
  completed: "status.completed",
  authorized: "status.authorized",
  supported: "status.supported",
  blocked: "status.blocked",
  pending: "status.pending",
  needs_user_action: "status.needsUserAction",
  unavailable: "status.unavailable",
  failed: "status.failed",
  broken: "status.broken",
  error: "status.error",
  running: "status.running",
  cancelled: "status.cancelled",
  awaiting_input: "status.awaitingInput",
  waiting: "status.waiting",
  unsupported: "status.unsupported",
  unknown: "status.unknown",
  not_observed: "status.notObserved",
  verified: "status.verified",
  active: "status.active",
  planned: "status.planned",
  prepared: "status.prepared",
  applying: "status.applying",
  finishing: "status.finishing",
  review: "status.review",
  applied: "status.applied",
  removed: "status.removed",
  restart_observed: "status.restartObserved",
  done: "status.done",
};

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  const text = useText();
  return (
    <header className="page-header">
      <div className="min-w-0">
        <p className="eyebrow">{eyebrow ?? text("common.workspace")}</p>
        <h1 className="page-title">{title}</h1>
        <p className="page-sub">{description}</p>
      </div>
      {action}
    </header>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <CircleDashed
        size={28}
        className="text-muted-foreground"
        aria-hidden="true"
      />
      <h2 className="section-title">{title}</h2>
      <p className="max-w-md text-sm text-muted-foreground">{children}</p>
      {action}
    </div>
  );
}

export function StatusBadge({
  state,
  children,
}: {
  state: string;
  children?: ReactNode;
}) {
  const text = useText();
  const good = ["ready", "completed", "authorized", "supported"].includes(
    state,
  );
  const warning = [
    "blocked",
    "pending",
    "needs_user_action",
    "unavailable",
  ].includes(state);
  const bad = ["failed", "broken", "error"].includes(state);
  const Icon = good ? CircleCheck : warning || bad ? CircleAlert : CircleDashed;
  return (
    <span
      className={`status-badge ${good ? "status-good" : warning ? "status-warning" : bad ? "status-bad" : ""}`}
    >
      <Icon size={13} aria-hidden="true" />
      {children ??
        (statusMessages[state]
          ? text(statusMessages[state])
          : text("status.unrecognized", { state }))}
    </span>
  );
}

export function ActionLink({
  to,
  title,
  children,
}: {
  to: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <Link to={to} className="action-card">
      <div>
        <h2 className="section-title">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{children}</p>
      </div>
      <ArrowUpRight size={18} aria-hidden="true" />
    </Link>
  );
}
