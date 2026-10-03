import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Ban, Play, StepForward } from "lucide-react";
import { argvToCall } from "../argv";
import {
  cliApplyConfirmed,
  cliPlan,
  cmdMachineHelp,
  cmdRunRead,
  cmdTaskAnswer,
  cmdTaskCancel,
  cmdTaskContinue,
  cmdTaskIntents,
  cmdTaskStart,
  cmdTaskStatus,
  type CliContinuation,
  type CmdResult,
} from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";

interface Question {
  question_id: string;
  prompt: string;
  value_type?: string;
  choices?: string[];
  recommended?: string;
  why?: string;
  actor?: string;
}

interface TaskView {
  task_id: string;
  revision: number;
  intent: string;
  state: string;
  goal_satisfied?: boolean;
  questions: Question[];
  outcome?: unknown;
}

// Fallback only: the live list comes from `task intents`, which publishes
// the same closed set `task start --intent` enforces. A CLI that cannot
// answer gets this — which is why it stays a constant.
const FALLBACK_INTENTS = [
  "install",
  "change",
  "switch",
  "initialize",
  "inspect",
  "author",
  "account",
  "publish",
  "technology",
];

/** Task-engine wizard: the CLI asks questions, we render them, the engine
 *  decides the next step. The app never guesses the flow — `questions[]`,
 *  `continuations[]` and `state` are the whole protocol. */
export default function InstallPage() {
  const [params] = useSearchParams();
  const [intent, setIntent] = useState(params.get("intent") ?? "install");
  const [intents, setIntents] = useState<string[]>(FALLBACK_INTENTS);
  const [task, setTask] = useState<TaskView | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [continuations, setContinuations] = useState<CliContinuation[]>([]);
  const [lastResult, setLastResult] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);
  // One idempotency key per logical Start click — a timeout-and-retry of
  // the same start hits the CLI's dedup instead of forking a second task.
  const [startKey, setStartKey] = useState<string | null>(null);

  useEffect(() => {
    const q = params.get("intent");
    if (q) setIntent(q);
  }, [params]);

  useEffect(() => {
    void cmdTaskIntents().then((r) => {
      const names = (
        (r.data?.intents as { name?: string }[] | undefined) ?? []
      )
        .map((i) => i.name)
        .filter((n): n is string => typeof n === "string" && n.length > 0);
      if (r.ok && names.length > 0) setIntents(names);
    });
  }, []);

  // Closing a journey ends the logical start it belonged to; the next Start
  // must mint a fresh key or the CLI reads it as the same start retried
  // with different input — a conflict, correctly refused.
  function closeTask() {
    setTask(null);
    setStartKey(null);
    setContinuations([]);
  }

  function view(r: CmdResult): TaskView | null {
    return (r.data as unknown as TaskView) ?? null;
  }

  async function refresh(taskId: string) {
    const r = await cmdTaskStatus(taskId);
    if (r.ok && r.data) setTask(view(r));
    return r;
  }

  async function start() {
    setBusy(true);
    try {
      setAnswers({});
      const key = startKey ?? `desktop-${Date.now().toString(36)}`;
      setStartKey(key);
      const r = await cmdTaskStart(intent, key);
      setLastResult(r);
      setContinuations(r.continuations);
      if (r.ok) setTask(view(r));
    } finally {
      setBusy(false);
    }
  }

  async function submitAnswers() {
    if (!task) return;
    setBusy(true);
    try {
      let current = task;
      // External-actor questions are informational — the engine answers
      // them itself; only human questions are submitted from the UI.
      for (const q of task.questions.filter((q) => q.actor !== "external")) {
        const v = answers[q.question_id] ?? q.recommended ?? "";
        if (v === "") {
          setLastResult({
            ok: false, data: null, warnings: [], continuations: [],
            error: `missing answer: ${q.question_id}`, error_code: "UI_VALIDATION",
          });
          return;
        }
        const r = await cmdTaskAnswer(
          current.task_id,
          String(current.revision),
          q.question_id,
          v,
        );
        setLastResult(r);
        setContinuations(r.continuations);
        if (!r.ok) return;
        if (r.data) current = r.data as unknown as TaskView;
        setTask(current);
        await refresh(current.task_id).then((rr) => {
          if (rr.ok && rr.data) current = rr.data as unknown as TaskView;
        });
        setTask(current);
      }
      setAnswers({});
    } finally {
      setBusy(false);
    }
  }

  async function continueTask() {
    if (!task) return;
    setBusy(true);
    try {
      const r = await cmdTaskContinue(task.task_id, String(task.revision));
      setLastResult(r);
      setContinuations(r.continuations);
      if (r.ok) await refresh(task.task_id);
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!task) return;
    setBusy(true);
    try {
      const r = await cmdTaskCancel(task.task_id, String(task.revision));
      setLastResult(r);
      if (r.ok) closeTask();
    } finally {
      setBusy(false);
    }
  }

  async function runContinuation(c: CliContinuation) {
    const callArgs = argvToCall(c.path, c.argv);
    if (!callArgs) {
      setLastResult({
        ok: false, data: null, warnings: [], continuations: [],
        error: `cannot translate continuation argv: ${c.argv.join(" ")}`,
        error_code: "UI_UNSUPPORTED_CONTINUATION",
      });
      return;
    }
    setBusy(true);
    try {
      const help = await cmdMachineHelp();
      const mut = (
        ((help.data ?? {}) as Record<string, unknown>).commands as
          | { path: string[]; mutability: string }[]
          | undefined
      )?.find((d) => d.path.join(" ") === callArgs.path)?.mutability;
      let r: CmdResult;
      if (mut === "read")
        r = await cmdRunRead(callArgs.path, callArgs.values, callArgs.flags, callArgs.repeated);
      else if (mut === "plan")
        r = await cliPlan(callArgs.path, callArgs.values, callArgs.flags, callArgs.repeated);
      else if (mut === "apply")
        r = await cliApplyConfirmed(callArgs.path, callArgs.values, callArgs.flags, true, callArgs.repeated);
      else
        r = {
          ok: false, data: null, warnings: [], continuations: [],
          error: `continuation to ${callArgs.path} (mutability=${mut ?? "unknown"}) is not runnable from the UI`,
          error_code: "UI_UNSUPPORTED_CONTINUATION",
        };
      setLastResult(r);
      setContinuations(r.continuations);
      if (task) await refresh(task.task_id);
    } finally {
      setBusy(false);
    }
  }

  const terminal = task && ["completed", "failed", "cancelled"].includes(task.state);
  // Only `actor === "cli"` continuations are runnable. Everything else —
  // external, human, agent, or an absent/unknown actor — is poll-only
  // status per ADR-0222 (fail-closed, matching the core's actor_kind()).
  const pendingContinuations = continuations.filter(
    (c) => c.actor === "cli" && c.argv.length > 0 && c.path.join(" ") !== "task answer",
  );
  const externalContinuations = continuations.filter(
    (c) => c.actor !== "cli" && c.path.join(" ") !== "task answer",
  );

  return (
    <div className="space-y-5">
      <header>
        <h1 className="page-title">Install &amp; flows</h1>
        <p className="page-sub">
          The task engine drives every journey: it asks, you answer, it plans,
          you approve the digest, it applies. Nothing is written before that approval.
        </p>
      </header>

      {!task && (
        <section className="card max-w-xl space-y-3 p-4">
          <h2 className="section-title">Start a flow</h2>
          <div className="flex flex-wrap gap-2">
            {intents.map((it) => (
              <button
                key={it}
                onClick={() => {
                  setIntent(it);
                  setStartKey(null);
                }}
                className={`rounded-sm border px-3 py-1.5 text-sm ${
                  intent === it
                    ? "border-primary bg-primary/10 font-medium text-primary"
                    : "border-input text-muted-foreground"
                }`}
              >
                {it}
              </button>
            ))}
          </div>
          <button onClick={() => void start()} disabled={busy} className="btn-primary">
            <Play size={14} /> Start
          </button>
        </section>
      )}

      {task && (
        <section className="card space-y-3 p-4">
          <div className="flex items-center justify-between">
            <h2 className="section-title">
              {task.intent} <span className="font-mono text-xs text-muted-foreground">{task.task_id}</span>
            </h2>
            <span className={`chip ${
              task.state === "completed" ? "bg-success/15 text-success"
              : task.state === "blocked" ? "bg-warning/15 text-warning"
              : "bg-muted text-muted-foreground"
            }`}>{task.state} · rev {task.revision}</span>
          </div>

          {task.questions.length > 0 && (
            <div className="space-y-3">
              {task.questions.map((q) =>
                q.actor === "external" ? (
                  <p key={q.question_id} className="text-xs text-muted-foreground">
                    ⓘ {q.prompt} — resolved by the engine, not you.
                  </p>
                ) : (
                <label key={q.question_id} className="block text-xs">
                  <span className="font-medium">{q.prompt}</span>
                  {q.why && <span className="ml-1 text-muted-foreground">— {q.why}</span>}
                  {q.choices && q.choices.length > 0 ? (
                    <select
                      value={answers[q.question_id] ?? q.recommended ?? ""}
                      onChange={(e) =>
                        setAnswers((a) => ({ ...a, [q.question_id]: e.target.value }))
                      }
                      className="input mt-1 w-full"
                    >
                      <option value="">—</option>
                      {q.choices.map((c) => <option key={c}>{c}</option>)}
                    </select>
                  ) : (
                    <input
                      value={answers[q.question_id] ?? q.recommended ?? ""}
                      onChange={(e) =>
                        setAnswers((a) => ({ ...a, [q.question_id]: e.target.value }))
                      }
                      className="input mt-1 w-full font-mono"
                    />
                  )}
                </label>
                ),
              )}
              {task.questions.some((q) => q.actor !== "external") && (
                <button onClick={() => void submitAnswers()} disabled={busy} className="btn-primary">
                  <StepForward size={14} /> Submit answers
                </button>
              )}
            </div>
          )}

          {task.outcome != null && (
            <section className="space-y-2">
              <h3 className="section-title">Outcome</h3>
              <Json v={task.outcome} />
            </section>
          )}

          {pendingContinuations.length > 0 && (
            <div className="space-y-2">
              <h3 className="section-title">Engine requests</h3>
              {pendingContinuations.map((c, i) => (
                <div key={i} className="space-y-1">
                  <button
                    onClick={() => void runContinuation(c)}
                    disabled={busy}
                    className="btn-danger"
                  >
                    Approve &amp; run: <code className="font-mono text-xs">{c.path.join(" ")}</code>
                  </button>
                  {c.argv.length > 0 && (
                    <p className="break-all font-mono text-[10px] text-muted-foreground">
                      {c.argv.join(" ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          {externalContinuations.length > 0 && (
            <div className="space-y-2">
              <h3 className="section-title">Waiting on external work</h3>
              <p className="text-xs text-muted-foreground">
                The engine delegated these steps outside the UI — poll status
                until they clear. They are informational, not runnable here.
              </p>
              <ul className="card divide-y divide-border text-xs">
                {externalContinuations.map((c, i) => (
                  <li key={i} className="flex items-center gap-2 px-3 py-1.5">
                    <span className="chip bg-warning/15 text-warning">{c.actor}</span>
                    <code className="font-mono">{c.path.join(" ")}</code>
                    {c.missing.length > 0 && (
                      <span className="text-muted-foreground">needs: {c.missing.join(", ")}</span>
                    )}
                  </li>
                ))}
              </ul>
              {task && (
                <button
                  onClick={() => void refresh(task.task_id)}
                  disabled={busy}
                  className="btn-outline"
                >
                  Refresh status
                </button>
              )}
            </div>
          )}

          <div className="flex gap-2">
            <button onClick={() => void continueTask()} disabled={busy || !!terminal} className="btn-outline">
              <StepForward size={14} /> Continue
            </button>
            <button onClick={() => void cancel()} disabled={busy || !!terminal} className="btn-outline">
              <Ban size={14} /> Cancel task
            </button>
            <button onClick={closeTask} disabled={busy} className="btn-outline">
              Close
            </button>
          </div>
        </section>
      )}

      {busy && <Spinner label="Talking to the task engine" />}
      {lastResult && <ResultMeta r={lastResult} />}
      {lastResult?.data && <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">Last envelope</summary><Json v={lastResult.data} /></details>}
    </div>
  );
}
