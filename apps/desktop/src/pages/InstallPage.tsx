import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowRight, Ban, RefreshCw, StepForward } from "lucide-react";
import {
  cmdTaskIntents,
  cmdTaskStatus,
  cmdTaskAnswer,
  cmdTaskContinue,
  cmdTaskCancel,
  cmdMachineHelp,
  cmdRunRead,
  cliApplyConfirmed,
  cliPlan,
  type CmdResult,
  type CliContinuation,
} from "../transport";
import {
  isTask,
  settled,
  type Descriptor,
  type TaskIntent,
  type TaskView,
} from "../contracts";
import { useTaskStart } from "../taskStart";
import { useApp } from "../store";
import { argvToCall } from "../argv";
import TaskOutcome from "../components/TaskOutcome";
import TaskOwnership from "../components/TaskOwnership";
import { Details, Json, ResultMeta, Spinner } from "../components/Result";
import { PageHeader, StatusBadge } from "../components/Layout";
import InstallInput, {
  emptyInstall,
  installComplete,
  installInput,
} from "../components/InstallInput";

function checkedTask(response: CmdResult, id: string): CmdResult {
  if (!response.ok || (isTask(response.data) && response.data.task_id === id)) return response;
  return { ok: false, data: null, error_code: "DESKTOP_TASK_CONTRACT",
    error: "The engine reply does not describe the requested task and supported ownership.",
    warnings: [], continuations: [] };
}

export default function InstallPage() {
  const [params, setParams] = useSearchParams();
  const taskId = params.get("task");
  const activeTask = useRef(taskId);
  activeTask.current = taskId;
  const [intent, setIntent] = useState(params.get("intent") ?? "install");
  const [intentResult, setIntentResult] = useState<CmdResult | null>(null);
  const [inputSchema, setInputSchema] = useState<CmdResult | null>(null);
  const [mode, setMode] = useState("form");
  const [inputPath, setInputPath] = useState("");
  const [fields, setFields] = useState(() => ({
    ...emptyInstall,
    setup: params.get("setup") ?? "",
    version: params.get("version") ?? "",
    digest: params.get("digest") ?? "",
    harness: params.get("harness") ?? "",
  }));
  const [task, setTask] = useState<TaskView | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [continuations, setContinuations] = useState<CliContinuation[]>([]);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const starter = useTaskStart();
  const capabilities = useApp((state) => state.capabilities);
  const current = useRef(true);
  const generation = useRef(0);
  const reads = useRef(0);
  useEffect(() => {
    current.current = true;
    return () => {
      current.current = false;
    };
  }, []);
  useEffect(() => {
    if (!taskId && params.get("intent")) {
      setIntent(params.get("intent")!);
      setConfirmed(false);
    }
  }, [params, taskId]);
  useEffect(() => {
    let active = true;
    void cmdTaskIntents().then((r) => {
      if (active) setIntentResult(r);
    });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    let active = true;
    setInputSchema(null);
    void cmdRunRead("task input-schema", { intent }).then((r) => {
      if (active) setInputSchema(r);
    });
    return () => {
      active = false;
    };
  }, [intent]);
  useEffect(() => {
    let active = true;
    const epoch = ++generation.current;
    const request = ++reads.current;
    setTask(null);
    setResult(null);
    setAnswers({});
    setContinuations([]);
    setBusy(false);
    if (taskId) {
      setBusy(true);
      void cmdTaskStatus(taskId).then((response) => {
        if (!active || generation.current !== epoch || reads.current !== request) return;
        const r = checkedTask(response, taskId);
        setResult(r);
        if (isTask(r.data)) setTask(r.data);
        setContinuations(r.continuations);
        setBusy(false);
      });
    }
    return () => {
      active = false;
      generation.current++;
      reads.current++;
    };
  }, [taskId]);
  useEffect(() => {
    if (taskId || starter.busy || !starter.result || starter.opened) return;
    const id = isTask(starter.result.data)
      ? starter.result.data.task_id
      : starter.result.error_details?.task_id;
    if (typeof id === "string") {
      setParams({ task: id });
      starter.acknowledge();
    }
  }, [
    taskId,
    starter.busy,
    starter.result,
    starter.opened,
    starter.acknowledge,
    params,
    setParams,
  ]);

  async function refresh(id: string, showResult = true) {
    const epoch = generation.current;
    const request = ++reads.current;
    setBusy(true);
    try {
      const response = checkedTask(await cmdTaskStatus(id), id);
      if (current.current && activeTask.current === id && generation.current === epoch && reads.current === request) {
        if (isTask(response.data)) {
          setTask(response.data);
          setAnswers({});
        } else if (response.error_code === "DESKTOP_TASK_CONTRACT") {
          setTask(null);
          setAnswers({});
        }
        setContinuations(response.continuations);
        if (showResult || !response.ok) setResult(response);
      }
      return response;
    } finally {
      if (current.current && activeTask.current === id && generation.current === epoch && reads.current === request) setBusy(false);
    }
  }
  async function step(action: () => Promise<CmdResult>) {
    if (!task || busy || activeTask.current !== task.task_id) return;
    const epoch = generation.current;
    setBusy(true);
    try {
      const returned = await action();
      const response = returned.ok && returned.data && "task_id" in returned.data
        ? checkedTask(returned, task.task_id) : returned;
      if (!current.current || activeTask.current !== task.task_id || generation.current !== epoch) return;
      setResult(response);
      if (isTask(response.data) && response.data.task_id === task.task_id) setTask(response.data);
      await refresh(task.task_id, false);
    } finally {
      if (current.current && activeTask.current === task.task_id && generation.current === epoch)
        setBusy(false);
    }
  }
  async function submitAnswer(questionId: string, value: string) {
    if (!task || !value) return;
    await step(() =>
      cmdTaskAnswer(task.task_id, String(task.revision), questionId, value),
    );
  }
  async function runContinuation(continuation: CliContinuation) {
    if (!task) return;
    await step(async () => {
      const args = argvToCall(continuation.path, continuation.argv);
      const help = await cmdMachineHelp();
      const descriptor = (
        help.data?.commands as Descriptor[] | undefined
      )?.find((item) => item.path.join(" ") === args?.path);
      if (!args || !descriptor)
        return {
          ok: false,
          data: null,
          warnings: [],
          continuations: [],
          error:
            "This continuation is not available in the connected command registry.",
          error_code: "DESKTOP_UNSUPPORTED_CONTINUATION",
        };
      if (descriptor.mutability === "read")
        return cmdRunRead(args.path, args.values, args.flags, args.repeated);
      if (descriptor.mutability === "plan")
        return cliPlan(args.path, args.values, args.flags, args.repeated);
      if (descriptor.mutability === "apply")
        return cliApplyConfirmed(
          args.path,
          args.values,
          args.flags,
          true,
          args.repeated,
        );
      return {
        ok: false,
        data: null,
        warnings: [],
        continuations: [],
        error: "Use the CLI for this continuation.",
        error_code: "DESKTOP_UNSUPPORTED_CONTINUATION",
      };
    });
  }
  function closeTask() {
    starter.reset();
    setParams({ intent });
    setTask(null);
    setResult(null);
    setConfirmed(false);
  }
  const intents = (intentResult?.data?.intents ?? []) as TaskIntent[];
  const unavailable =
    intent === "install" &&
    capabilities?.data?.configuration_installation !== "supported";
  const valid =
    mode === "file"
      ? !!inputPath.trim()
      : intent === "author" || (inputSchema?.ok && installComplete(fields));
  const locked = busy || starter.busy;
  const pendingStart = !taskId && !starter.opened && starter.result;
  const lastResult = result ?? pendingStart;
  return (
    <div className="page-stack">
      <PageHeader
        title={taskId ? "Task workspace" : "Your next setup"}
        description={
          taskId
            ? "Review the current state and continue through the engine's retained steps."
            : "Create from your files or install an exact setup into your chosen harness."
        }
        action={
          <Link className="btn-outline" to="/tasks">
            View activity
            <ArrowRight size={14} />
          </Link>
        }
      />
      {!taskId && (
        <section className="card space-y-6 p-6">
          <div className="flex flex-wrap gap-2" aria-label="Task intent">
            {intents.map((item) => (
              <button
                key={item.name}
                className={intent === item.name ? "btn-primary" : "btn-outline"}
                aria-pressed={intent === item.name}
                disabled={locked || !!pendingStart}
                onClick={() => {
                  setIntent(item.name);
                  setConfirmed(false);
                }}
              >
                {item.name === "install"
                  ? "Install a setup"
                  : item.name === "author"
                    ? "Create from files"
                    : item.name}
              </button>
            ))}
          </div>
          {!intentResult && <Spinner label="Reading available flows" />}
          {intentResult && !intentResult.ok && <ResultMeta r={intentResult} />}
          <p className="text-sm leading-6 text-muted-foreground">
            {intents.find((item) => item.name === intent)?.when}
          </p>
          <p className="text-sm text-muted-foreground">
            These flows create personal tasks. Selecting a company view does not
            make them company-managed installations.
          </p>
          {unavailable && (
            <div
              role="status"
              className="rounded-md border border-warning/40 bg-warning/5 p-4 text-sm"
            >
              {capabilities
                ? `Setup installation is unavailable on ${String(capabilities.data?.os ?? "this platform")}. Authoring and catalog browsing remain available.`
                : "Checking installation support…"}
            </div>
          )}
          {starter.busy && (
            <Spinner label="The engine is running this task. You can return through Activity." />
          )}
          {pendingStart && !isTask(pendingStart.data) && (
            <div className="space-y-3">
              <ResultMeta r={pendingStart} />
              <p className="text-sm text-muted-foreground">
                The last request is retained for an identical retry. If its
                effect is unconfirmed, inspect Activity before retrying.
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn-outline"
                  onClick={() => {
                    if (starter.request) void starter.start(starter.request);
                  }}
                >
                  Retry the same request
                </button>
                <Link className="btn-outline" to="/tasks">
                  Inspect activity
                </Link>
                <button
                  className="btn-outline"
                  onClick={() => {
                    starter.reset();
                    setConfirmed(false);
                  }}
                >
                  Edit a new request
                </button>
              </div>
            </div>
          )}
          <fieldset disabled={locked || !!pendingStart} className="space-y-5">
            <label className="field-label max-w-xs">
              Input method
              <select
                className="input"
                value={mode}
                onChange={(event) => {
                  setMode(event.target.value);
                  setConfirmed(false);
                }}
              >
                <option value="form">
                  {intent === "author"
                    ? "Guided questions"
                    : "Installation form"}
                </option>
                <option value="file">Existing JSON file (advanced)</option>
              </select>
            </label>
            {mode === "file" ? (
              <label className="field-label">
                Task input JSON file
                <input
                  className="input font-mono font-normal"
                  value={inputPath}
                  onChange={(event) => {
                    setInputPath(event.target.value);
                    setConfirmed(false);
                  }}
                  placeholder="Absolute path to the input file"
                />
                <p className="field-help">
                  The CLI reads and validates this file. Use it for advanced
                  access, trust pins and placement options.
                </p>
              </label>
            ) : intent === "install" ? (
              <InstallInput
                schema={inputSchema}
                fields={fields}
                setFields={(value) => {
                  setFields(value);
                  setConfirmed(false);
                }}
              />
            ) : (
              <p className="rounded-md bg-muted/50 p-4 text-sm leading-6">
                The engine will ask for your directory, harness, component kind,
                name and license. Answering the final question authorizes
                creation.
              </p>
            )}
            <label className="flex items-start gap-3 rounded-md border border-border p-4 text-sm">
              <input
                className="mt-1"
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              I authorize this request. Starting or answering can apply changes
              immediately after the engine validates the inputs.
            </label>
            <button
              className="btn-primary"
              disabled={
                !confirmed ||
                !valid ||
                unavailable ||
                !intents.some((item) => item.name === intent)
              }
              onClick={() =>
                void starter.start({
                  intent,
                  ...(mode === "file"
                    ? { inputPath: inputPath.trim() }
                    : intent === "install"
                      ? { input: installInput(fields) }
                      : {}),
                })
              }
            >
              Start {intent === "author" ? "authoring" : "installation"}
              <ArrowRight size={14} />
            </button>
          </fieldset>
          {inputSchema?.data && (
            <Details label="Accepted input schema" value={inputSchema.data} />
          )}
        </section>
      )}
      {taskId && busy && <Spinner label="Reading the latest task state" />}
      {task && (
        <section className="card space-y-6 p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="section-title capitalize">{task.intent} task</h2>
              <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                {task.task_id}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Revision {task.revision}
              </p>
            </div>
            <StatusBadge state={task.state} />
          </div>
          {task.legacy_read_only && (
            <p className="text-sm text-muted-foreground">
              This retained legacy task is read-only.
            </p>
          )}
          <TaskOwnership value={task.ownership} />
          {task.questions.map((question) =>
            question.actor === "external" || question.actor === "agent" ? (
              <p
                key={question.question_id}
                className="text-sm text-muted-foreground"
              >
                {question.prompt} · waiting for {question.actor}
              </p>
            ) : (
              <form
                key={`${task.revision}-${question.question_id}`}
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  void submitAnswer(
                    question.question_id,
                    answers[question.question_id] ?? question.recommended ?? "",
                  );
                }}
              >
                <label className="field-label">
                  {question.prompt}
                  {question.choices?.length ? (
                    <select
                      className="input"
                      disabled={locked}
                      value={
                        answers[question.question_id] ??
                        question.recommended ??
                        ""
                      }
                      onChange={(event) =>
                        setAnswers({
                          [question.question_id]: event.target.value,
                        })
                      }
                    >
                      <option value="">Choose…</option>
                      {question.choices.map((choice) => (
                        <option key={choice}>{choice}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      className="input"
                      disabled={locked}
                      value={
                        answers[question.question_id] ??
                        question.recommended ??
                        ""
                      }
                      onChange={(event) =>
                        setAnswers({
                          [question.question_id]: event.target.value,
                        })
                      }
                    />
                  )}
                </label>
                {question.why && <p className="field-help">{question.why}</p>}
                <button
                  className="btn-primary"
                  disabled={
                    locked ||
                    task.legacy_read_only ||
                    !(
                      answers[question.question_id] ??
                      question.recommended ??
                      ""
                    )
                  }
                >
                  <StepForward size={14} />
                  Submit answer
                </button>
              </form>
            ),
          )}
          {task.handoff != null && (
            <section className="space-y-3">
              <h3 className="section-title">Activation handoff</h3>
              <p className="text-sm text-muted-foreground">
                Follow the engine's restart instructions before continuing this
                task.
              </p>
              <Json v={task.handoff} />
            </section>
          )}
          {task.outcome != null && <TaskOutcome value={task.outcome} />}
          {continuations
            .filter((item) => item.path.join(" ") !== "task answer")
            .map((item, index) => (
              <div
                key={index}
                className="space-y-2 rounded-md border border-border p-4"
              >
                <p className="font-mono text-xs">{item.path.join(" ")}</p>
                {item.actor === "cli" &&
                item.argv.length > 0 &&
                !item.missing.length ? (
                  <>
                    <p className="break-all font-mono text-xs text-muted-foreground">
                      {item.argv.join(" ")}
                    </p>
                    <button
                      className="btn-outline"
                      disabled={locked || task.legacy_read_only}
                      onClick={() => void runContinuation(item)}
                    >
                      Approve and run this step
                    </button>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Waiting for {item.actor ?? "human"}
                    {item.missing.length
                      ? ` · needs ${item.missing.join(", ")}`
                      : ""}
                    . Refresh after completing the external step.
                  </p>
                )}
              </div>
            ))}
          <div className="flex flex-wrap gap-3 border-t border-border pt-5">
            <button
              className="btn-outline"
              disabled={locked}
              onClick={() => {
                void refresh(task.task_id);
              }}
            >
              <RefreshCw size={14} />
              Refresh
            </button>
            {!settled(task) && !task.legacy_read_only && (
              <>
                <button
                  className="btn-primary"
                  disabled={locked || !!task.questions.length}
                  onClick={() =>
                    void step(() =>
                      cmdTaskContinue(task.task_id, String(task.revision)),
                    )
                  }
                >
                  <StepForward size={14} />
                  Continue task
                </button>
                <button
                  className="btn-outline"
                  disabled={locked}
                  onClick={() =>
                    void step(() =>
                      cmdTaskCancel(task.task_id, String(task.revision)),
                    )
                  }
                >
                  <Ban size={14} />
                  Cancel task
                </button>
              </>
            )}
            <button
              className="btn-outline"
              disabled={locked}
              onClick={closeTask}
            >
              {settled(task) ? "Start another flow" : "Close view"}
            </button>
          </div>
        </section>
      )}
      {lastResult && !pendingStart && <ResultMeta r={lastResult} />}
      {taskId &&
        starter.result &&
        !starter.result.ok &&
        starter.result.error_details?.task_id === taskId && (
          <ResultMeta r={starter.result} />
        )}
      {taskId && !task && !busy && (
        <button className="btn-outline" onClick={closeTask}>
          Back to setups
        </button>
      )}
    </div>
  );
}
