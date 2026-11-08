import { useText } from "../i18n";
import { choiceLabel, intentGuidance, intentLabel } from "../labels";
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
  if (!response.ok) return { ...response, data: null };
  if (isTask(response.data) && response.data.task_id === id) return response;
  return {
    ok: false,
    data: null,
    error_code: "DESKTOP_TASK_CONTRACT",
    error:
      "The engine reply does not describe the requested task and supported ownership.",
    warnings: [],
    continuations: [],
  };
}

export default function InstallPage() {
  const msg = useText();
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
        if (
          !active ||
          generation.current !== epoch ||
          reads.current !== request
        )
          return;
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
      if (
        current.current &&
        activeTask.current === id &&
        generation.current === epoch &&
        reads.current === request
      ) {
        setTask(isTask(response.data) ? response.data : null);
        setAnswers({});
        setContinuations(response.continuations);
        if (showResult || !response.ok) setResult(response);
      }
      return response;
    } finally {
      if (
        current.current &&
        activeTask.current === id &&
        generation.current === epoch &&
        reads.current === request
      )
        setBusy(false);
    }
  }
  async function step(action: () => Promise<CmdResult>) {
    if (
      !task ||
      task.legacy_read_only ||
      busy ||
      activeTask.current !== task.task_id
    )
      return;
    const epoch = generation.current;
    setBusy(true);
    try {
      const returned = await action();
      if (
        !current.current ||
        activeTask.current !== task.task_id ||
        generation.current !== epoch
      )
        return;
      const response =
        returned.data &&
        typeof returned.data === "object" &&
        "task_id" in returned.data
          ? checkedTask(returned, task.task_id)
          : returned;
      setResult(response);
      if (isTask(response.data) && response.data.task_id === task.task_id)
        setTask(response.data);
      await refresh(task.task_id, false);
    } finally {
      if (
        current.current &&
        activeTask.current === task.task_id &&
        generation.current === epoch
      )
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
    const epoch = generation.current;
    await step(async () => {
      const args = argvToCall(continuation.path, continuation.argv);
      const help = await cmdMachineHelp();
      if (
        !current.current ||
        activeTask.current !== task.task_id ||
        generation.current !== epoch
      )
        return {
          ok: false,
          data: null,
          warnings: [],
          continuations: [],
          error:
            "This task view changed before the step was submitted. Review the original task again.",
          error_code: "DESKTOP_TASK_VIEW_CHANGED",
        };
      if (!help.ok) return help;
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
        title={
          taskId ? msg("install.taskWorkspace") : msg("install.yourNextSetup")
        }
        description={
          taskId
            ? msg("install.reviewTheCurrentStateAndContinueThroughTheEngine")
            : msg("install.createFromYourFilesOrInstallAnExactSetup")
        }
        action={
          <Link className="btn-outline" to="/tasks">
            {msg("install.viewActivity")}
            <ArrowRight size={14} />
          </Link>
        }
      />
      {!taskId && (
        <section className="card space-y-6 p-6">
          <div
            className="flex flex-wrap gap-2"
            aria-label={msg("install.taskIntent")}
          >
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
                {intentLabel(msg, item.name)}
              </button>
            ))}
          </div>
          {!intentResult && (
            <Spinner label={msg("install.readingAvailableFlows")} />
          )}
          {intentResult && !intentResult.ok && <ResultMeta r={intentResult} />}
          <p className="text-sm leading-6 text-muted-foreground">
            {intentGuidance(
              msg,
              intent,
              intents.find((item) => item.name === intent)?.when,
            )}
          </p>
          <p className="text-sm text-muted-foreground">
            {msg("install.theseFlowsCreatePersonalTasksSelectingACompanyView")}
          </p>
          {unavailable && (
            <div
              role="status"
              className="rounded-md border border-warning/40 bg-warning/5 p-4 text-sm"
            >
              {capabilities
                ? msg("install.platformUnavailable", {
                    platform: String(
                      capabilities.data?.os ?? msg("common.thisPlatform"),
                    ),
                  })
                : msg("install.checkingInstallationSupport")}
            </div>
          )}
          {starter.busy && (
            <Spinner
              label={msg("install.theEngineIsRunningThisTaskYouCanReturn")}
            />
          )}
          {pendingStart && !isTask(pendingStart.data) && (
            <div className="space-y-3">
              <ResultMeta r={pendingStart} />
              <p className="text-sm text-muted-foreground">
                {msg("install.theLastRequestIsRetainedForAnIdenticalRetry")}
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn-outline"
                  onClick={() => {
                    if (starter.request) void starter.start(starter.request);
                  }}
                >
                  {msg("install.retryTheSameRequest")}
                </button>
                <Link className="btn-outline" to="/tasks">
                  {msg("install.inspectActivity")}
                </Link>
                <button
                  className="btn-outline"
                  onClick={() => {
                    starter.reset();
                    setConfirmed(false);
                  }}
                >
                  {msg("install.editANewRequest")}
                </button>
              </div>
            </div>
          )}
          <fieldset disabled={locked || !!pendingStart} className="space-y-5">
            <label className="field-label max-w-xs">
              {msg("install.inputMethod")}
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
                    ? msg("install.guidedQuestions")
                    : msg("install.installationForm")}
                </option>
                <option value="file">
                  {msg("install.existingJsonFileAdvanced")}
                </option>
              </select>
            </label>
            {mode === "file" ? (
              <label className="field-label">
                {msg("install.taskInputJsonFile")}
                <input
                  className="input font-mono font-normal"
                  value={inputPath}
                  onChange={(event) => {
                    setInputPath(event.target.value);
                    setConfirmed(false);
                  }}
                  placeholder={msg("install.absolutePathToTheInputFile")}
                />
                <p className="field-help">
                  {msg("install.theCliReadsAndValidatesThisFileUseIt")}
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
                {msg(
                  "install.theEngineWillAskForYourDirectoryHarnessComponent",
                )}
              </p>
            )}
            <label className="flex items-start gap-3 rounded-md border border-border p-4 text-sm">
              <input
                className="mt-1"
                type="checkbox"
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              {msg("install.iAuthorizeThisRequestStartingOrAnsweringCanApply")}
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
              {msg("install.start")}{" "}
              {intent === "author"
                ? msg("install.authoring")
                : msg("install.installation")}
              <ArrowRight size={14} />
            </button>
          </fieldset>
          {inputSchema?.data && (
            <Details
              label={msg("install.acceptedInputSchema")}
              value={inputSchema.data}
            />
          )}
        </section>
      )}
      {taskId && busy && (
        <Spinner label={msg("install.readingTheLatestTaskState")} />
      )}
      {task && (
        <section className="card space-y-6 p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="section-title capitalize">
                {task.intent} {msg("install.task")}
              </h2>
              <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                {task.task_id}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {msg("install.revision")} {task.revision}
              </p>
            </div>
            <StatusBadge state={task.state} />
          </div>
          {task.legacy_read_only && (
            <p className="text-sm text-muted-foreground">
              {msg("install.thisRetainedLegacyTaskIsReadOnly")}
            </p>
          )}
          <TaskOwnership value={task.ownership} />
          {task.questions.map((question) =>
            question.actor === "external" || question.actor === "agent" ? (
              <p
                key={question.question_id}
                className="text-sm text-muted-foreground"
              >
                {question.prompt} {msg("install.waitingFor")} {question.actor}
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
                      <option value="">{msg("install.choose")}</option>
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
                  {msg("install.submitAnswer")}
                </button>
              </form>
            ),
          )}
          {task.handoff != null && (
            <section className="space-y-3">
              <h3 className="section-title">
                {msg("install.activationHandoff")}
              </h3>
              <p className="text-sm text-muted-foreground">
                {msg(
                  "install.followTheEngineSRestartInstructionsBeforeContinuingThis",
                )}
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
                      {msg("install.approveAndRunThisStep")}
                    </button>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {msg("install.waitingFor2")}{" "}
                    {choiceLabel(msg, item.actor ?? "human")}
                    {item.missing.length
                      ? msg("install.missingParameters", {
                          parameters: item.missing.join(", "),
                        })
                      : ""}
                    {msg("install.refreshAfterCompletingTheExternalStep")}
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
              {msg("common.refresh")}
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
                  {msg("install.continueTask")}
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
                  {msg("install.cancelTask")}
                </button>
              </>
            )}
            <button
              className="btn-outline"
              disabled={locked}
              onClick={closeTask}
            >
              {settled(task)
                ? msg("install.startAnotherFlow")
                : msg("install.closeView")}
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
        <div className="flex flex-wrap gap-3">
          <button className="btn-outline" onClick={() => void refresh(taskId)}>
            {msg("install.readTaskAgain")}
          </button>
          <button className="btn-outline" onClick={closeTask}>
            {msg("install.backToSetups")}
          </button>
        </div>
      )}
    </div>
  );
}
