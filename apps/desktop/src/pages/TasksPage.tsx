import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ArrowRight, RefreshCw } from "lucide-react";
import { cmdTaskList, type CmdResult } from "../transport";
import { ResultMeta, Spinner } from "../components/Result";
import { EmptyState, PageHeader, StatusBadge } from "../components/Layout";

export default function TasksPage() {
  const [list, setList] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [inspectId, setInspectId] = useState("");
  async function refresh() {
    setBusy(true);
    try {
      setList(await cmdTaskList());
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    let current = true;
    void cmdTaskList().then((result) => {
      if (current) setList(result);
    });
    return () => {
      current = false;
    };
  }, []);
  const tasks = (list?.data?.tasks ?? []) as {
    task_id: string;
    intent: string;
    state: string;
    harness_id?: string;
    updated_at?: string;
  }[];
  return (
    <div className="page-stack">
      <PageHeader
        title="Activity"
        description="Resume open tasks or inspect any retained task by its ID."
        action={
          <button
            className="btn-outline"
            onClick={() => void refresh()}
            disabled={busy}
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        }
      />
      <section className="card space-y-3 p-5">
        <h2 className="section-title">Open a retained task</h2>
        <div className="flex gap-3">
          <input
            aria-label="Task ID"
            className="input min-w-0 font-mono"
            value={inspectId}
            onChange={(event) => setInspectId(event.target.value)}
            placeholder="task_…"
          />
          <Link
            aria-disabled={!inspectId.trim()}
            onClick={(event) => {
              if (!inspectId.trim()) event.preventDefault();
            }}
            className="btn-outline shrink-0"
            to={`/install?task=${encodeURIComponent(inspectId.trim())}`}
          >
            Open task
            <ArrowRight size={14} />
          </Link>
        </div>
      </section>
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="section-title">Open tasks</h2>
          <Link className="text-sm text-primary" to="/install">
            Start a flow
          </Link>
        </div>
        {(!list || busy) && <Spinner label="Reading task history" />}
        {list && <ResultMeta r={list} />}
        {list?.ok && tasks.length === 0 && (
          <EmptyState title="All clear">
            There are no unfinished tasks. Completed tasks remain available by
            their ID.
            <Link className="btn-outline mt-5" to="/install">
              Create or install a setup
              <ArrowRight size={14} />
            </Link>
          </EmptyState>
        )}
        {tasks.length > 0 && (
          <ul className="card divide-y divide-border overflow-hidden">
            {tasks.map((task) => (
              <li key={task.task_id}>
                <Link
                  to={`/install?task=${encodeURIComponent(task.task_id)}`}
                  className="flex items-center justify-between gap-5 px-5 py-4 hover:bg-accent"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium capitalize">
                      {task.intent}
                      {task.harness_id ? ` · ${task.harness_id}` : ""}
                    </p>
                    <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
                      {task.task_id}
                    </p>
                    {task.updated_at && (
                      <p className="mt-2 text-xs text-muted-foreground">
                        Updated {new Date(task.updated_at).toLocaleString()}
                      </p>
                    )}
                  </div>
                  <StatusBadge state={task.state} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
