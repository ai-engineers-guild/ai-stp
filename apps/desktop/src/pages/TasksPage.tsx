import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Play } from "lucide-react";
import {
  cmdTaskIntents,
  cmdTaskList,
  cmdTaskStatus,
  type CmdResult,
} from "../transport";
import { Json, ResultMeta } from "../components/Result";

/** Durable task journeys. Progress is phases/status, not fake percentages —
 * the CLI has no streaming progress protocol, so we poll `task status`. */
export default function TasksPage() {
  const [intents, setIntents] = useState<CmdResult | null>(null);
  const [list, setList] = useState<CmdResult | null>(null);

  const [status, setStatus] = useState<CmdResult | null>(null);
  const [inspectId, setInspectId] = useState("");

  useEffect(() => {
    void (async () => {
      setIntents(await cmdTaskIntents());
      setList(await cmdTaskList());
    })();
  }, []);

  async function pollOnce(id: string) {
    setStatus(await cmdTaskStatus(id));
  }

  // Starting a journey lives on the Install & flows page — it owns the
  // question loop. This page watches the durable status of tasks started
  // anywhere.

  const intentsData = (intents?.data ?? {}) as Record<string, unknown>;
  const listData = (list?.data ?? {}) as Record<string, unknown>;
  const intentList = (intentsData.intents ?? intentsData.items ?? []) as Array<
    Record<string, unknown>
  >;
  const taskList = (listData.tasks ?? listData.items ?? []) as Array<
    Record<string, unknown>
  >;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="page-title">Tasks</h1>
        <p className="text-sm text-muted-foreground">
          Long-running journeys (install, switch, sync) with durable status and recovery.
        </p>
      </header>

      <section>
        <h2 className="mb-2 section-title">Available intents</h2>
        {intents && !intents.ok && <ResultMeta r={intents} />}
        {intentList.length === 0 && intents?.ok && (
          <p className="text-sm text-muted-foreground">No intents reported.</p>
        )}
        <div className="flex flex-wrap gap-2">
          {intentList.map((it, i) => {
            const name = String(it.intent ?? it.name ?? it.id ?? "");
            return (
              <Link
                key={i}
                to={`/install?intent=${encodeURIComponent(name)}`}
                className="flex items-center gap-1.5 rounded-lg border border-input px-3 py-1.5 text-sm hover:bg-accent"
              >
                <Play size={12} /> {name}
              </Link>
            );
          })}
        </div>
      </section>



      <section className="space-y-2">
        <h2 className="section-title">Inspect a task</h2>
        <div className="flex gap-2">
          <input
            value={inspectId}
            onChange={(e) => setInspectId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && inspectId.trim() && void pollOnce(inspectId.trim())}
            placeholder="task_01…"
            className="input w-72 font-mono"
          />
          <button
            onClick={() => void pollOnce(inspectId.trim())}
            disabled={!inspectId.trim()}
            className="btn-outline"
          >
            Check status
          </button>
        </div>
        {status && (
          <>
            <ResultMeta r={status} />
            {status.data && <Json v={status.data} />}
          </>
        )}
      </section>

      <section>
        <h2 className="mb-2 section-title">Recent tasks</h2>
        {list && !list.ok && <ResultMeta r={list} />}
        {list?.ok && taskList.length === 0 && (
          <p className="text-sm text-muted-foreground">None yet.</p>
        )}
        {taskList.length > 0 && (
          <ul className="divide-y divide-border card">
            {taskList.map((t, i) => {
              const id = String(t.task_id ?? t.id ?? "");
              return (
                <li key={i}>
                  <button
                    onClick={() => {
                      setInspectId(id);
                      void pollOnce(id);
                    }}
                    className="flex w-full items-center justify-between px-4 py-2 text-left text-sm hover:bg-accent"
                  >
                    <span className="font-mono text-xs">{id}</span>
                    <span className="text-xs">{String(t.intent ?? "")}</span>
                    <span className="text-xs font-semibold">
                      {String(t.state ?? t.status ?? "")}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
