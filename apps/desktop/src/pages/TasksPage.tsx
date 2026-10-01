import { useEffect, useRef, useState } from "react";
import { Play } from "lucide-react";
import {
  cmdTaskIntents,
  cmdTaskList,
  cmdTaskStart,
  cmdTaskStatus,
  type CmdResult,
} from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";

/** Durable task journeys. Progress is phases/status, not fake percentages —
 * the CLI has no streaming progress protocol, so we poll `task status`. */
export default function TasksPage() {
  const [intents, setIntents] = useState<CmdResult | null>(null);
  const [list, setList] = useState<CmdResult | null>(null);
  const [started, setStarted] = useState<CmdResult | null>(null);
  const [status, setStatus] = useState<CmdResult | null>(null);
  const [taskId, setTaskId] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    void (async () => {
      setIntents(await cmdTaskIntents());
      setList(await cmdTaskList());
    })();
    return () => stopPoll();
  }, []);

  function stopPoll() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startPoll(id: string) {
    stopPoll();
    pollRef.current = setInterval(async () => {
      const r = await cmdTaskStatus(id);
      setStatus(r);
      const s = String((r.data as Record<string, unknown> | null)?.status ?? "");
      if (["completed", "failed", "cancelled", "rejected"].includes(s)) stopPoll();
    }, 3000);
  }

  async function start(intent: string) {
    const r = await cmdTaskStart(intent);
    setStarted(r);
    const d = (r.data ?? {}) as Record<string, unknown>;
    const id = String(d.task_id ?? d.id ?? "");
    if (r.ok && id) {
      setTaskId(id);
      startPoll(id);
    }
    setList(await cmdTaskList());
  }

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
        <h1 className="text-xl font-bold">Tasks</h1>
        <p className="text-sm opacity-60">
          Long-running journeys (install, switch, sync) with durable status and recovery.
        </p>
      </header>

      <section>
        <h2 className="mb-2 text-sm font-semibold">Available intents</h2>
        {intents && !intents.ok && <ResultMeta r={intents} />}
        {intentList.length === 0 && intents?.ok && (
          <p className="text-sm opacity-60">No intents reported.</p>
        )}
        <div className="flex flex-wrap gap-2">
          {intentList.map((it, i) => {
            const name = String(it.intent ?? it.name ?? it.id ?? "");
            return (
              <button
                key={i}
                onClick={() => void start(name)}
                className="flex items-center gap-1.5 rounded-lg border border-current/20 px-3 py-1.5 text-sm hover:bg-black/5 dark:hover:bg-white/5"
              >
                <Play size={12} /> {name}
              </button>
            );
          })}
        </div>
      </section>

      {started && (
        <section className="space-y-2">
          <ResultMeta r={started} />
          {started.data && <Json v={started.data} />}
        </section>
      )}

      {taskId && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">
            Status <span className="font-mono text-xs opacity-60">{taskId}</span>
          </h2>
          {status ? (
            <>
              <ResultMeta r={status} />
              {status.data && <Json v={status.data} />}
            </>
          ) : (
            <Spinner label="Polling task status" />
          )}
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold">Recent tasks</h2>
        {taskList.length === 0 ? (
          <p className="text-sm opacity-60">None yet.</p>
        ) : (
          <ul className="divide-y divide-current/10 rounded-xl border border-current/15">
            {taskList.map((t, i) => (
              <li key={i} className="flex items-center justify-between px-4 py-2 text-sm">
                <span className="font-mono text-xs">{String(t.task_id ?? t.id ?? "")}</span>
                <span className="text-xs">{String(t.intent ?? "")}</span>
                <span className="text-xs font-semibold">{String(t.status ?? "")}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
