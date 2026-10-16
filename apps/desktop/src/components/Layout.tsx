import type { ReactNode } from "react";
import {
  ArrowUpRight,
  CircleCheck,
  CircleAlert,
  CircleDashed,
} from "lucide-react";
import { Link } from "react-router";

export function PageHeader({
  eyebrow = "Workspace",
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="min-w-0">
        <p className="eyebrow">{eyebrow}</p>
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
      {children ?? state.replaceAll("_", " ")}
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
