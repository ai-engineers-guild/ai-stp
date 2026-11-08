import { useText } from "../i18n";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Search, Play } from "lucide-react";
import {
  cliApplyConfirmed,
  cliPlan,
  cmdMachineHelp,
  cmdRunRead,
  type CmdResult,
} from "../transport";
import type { Descriptor } from "../contracts";
import { Json, ResultMeta, Spinner } from "../components/Result";
import { EmptyState, PageHeader, StatusBadge } from "../components/Layout";
import { useApp } from "../store";

/** Descriptor-driven advanced operations; the native process validates every rule. */
export default function RegistryPage({
  title,
  description,
  prefixes = [],
}: {
  title?: string;
  description?: string;
  prefixes?: string[];
}) {
  const msg = useText();
  const [params] = useSearchParams();
  const [help, setHelp] = useState<CmdResult | null>(null);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Descriptor | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [flags, setFlags] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let current = true;
    void cmdMachineHelp().then((r) => {
      if (current) setHelp(r);
    });
    return () => {
      current = false;
    };
  }, []);
  const commands = ((help?.data?.commands ?? []) as Descriptor[]).filter(
    (command) => {
      const path = command.path.join(" ");
      return (
        !prefixes.length ||
        prefixes.some(
          (prefix) => path === prefix || path.startsWith(`${prefix} `),
        )
      );
    },
  );
  useEffect(() => {
    const requested = params.get("command");
    if (requested && help?.ok) {
      const command = commands.find(
        (command) => command.path.join(" ") === requested,
      );
      if (command) select(command);
    }
  }, [params, help]);
  function select(command: Descriptor) {
    setSelected(command);
    setValues({});
    setFlags([]);
    setConfirmed(false);
    setResult(null);
  }
  const shown = commands.filter((command) =>
    `${command.path.join(" ")} ${command.summary}`
      .toLowerCase()
      .includes(filter.toLowerCase()),
  );
  const missing = selected?.parameters.some(
    (parameter) =>
      parameter.required &&
      (parameter.value_type === "boolean"
        ? !flags.includes(parameter.name)
        : !values[parameter.name]?.trim()),
  );
  const runnable =
    selected && ["read", "plan", "apply"].includes(selected.mutability);
  async function run() {
    if (!selected || !runnable || busy) return;
    setBusy(true);
    try {
      const scalar: Record<string, string> = {};
      const repeated: Record<string, string[]> = {};
      for (const parameter of selected.parameters) {
        const value = values[parameter.name];
        if (!value) continue;
        if (parameter.repeatable)
          repeated[parameter.name] = value.split("\n").filter(Boolean);
        else scalar[parameter.name] = value;
      }
      const path = selected.path.join(" ");
      const response = await (selected.mutability === "read"
        ? cmdRunRead(path, scalar, flags, repeated)
        : selected.mutability === "plan"
          ? cliPlan(path, scalar, flags, repeated)
          : cliApplyConfirmed(path, scalar, flags, confirmed, repeated));
      setResult(response);
      setConfirmed(false);
      if (response.ok && selected.mutability === "apply") {
        void useApp.getState().refreshCli();
        void useApp.getState().refreshAuth();
      }
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={msg("registry.tools")}
        title={title ?? msg("shell.commands")}
        description={description ?? msg("registry.description")}
      />
      {!help && <Spinner label={msg("registry.readingAvailableCommands")} />}
      {help && !help.ok && <ResultMeta r={help} />}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(250px,0.8fr)_minmax(0,1.2fr)]">
        <section
          className="card overflow-hidden"
          aria-label={msg("registry.availableCommands")}
        >
          <div className="border-b border-border p-3">
            <label className="relative block">
              <Search
                size={15}
                className="absolute start-3 top-3 text-muted-foreground"
              />
              <input
                aria-label={msg("registry.filterCommands")}
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder={msg("registry.findACommand")}
                className="input ps-9"
              />
            </label>
          </div>
          <div className="px-4 py-2 text-xs text-muted-foreground">
            {shown.length} {msg("registry.operations")}
          </div>
          <ul className="max-h-[55vh] divide-y divide-border overflow-y-auto text-sm">
            {shown.map((command) => (
              <li key={command.path.join(" ")}>
                <button
                  aria-pressed={selected === command}
                  className={`w-full p-4 text-start hover:bg-accent ${selected === command ? "bg-primary/5" : ""}`}
                  disabled={busy}
                  onClick={() => select(command)}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-mono text-xs">
                      {command.path.join(" ")}
                    </span>
                    <span className="chip bg-muted text-muted-foreground">
                      {command.mutability}
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
                    {command.summary}
                  </p>
                </button>
              </li>
            ))}
          </ul>
          {help?.ok && !shown.length && (
            <p className="p-5 text-sm text-muted-foreground">
              {msg("registry.noMatchingOperations")}
            </p>
          )}
        </section>
        <div className="min-w-0 space-y-5">
          {!selected ? (
            <EmptyState title={msg("registry.chooseAnOperation")}>
              {msg("registry.readItsDescriptionReviewTheAcceptedInputsThenRun")}
            </EmptyState>
          ) : (
            <form
              className="card space-y-5 p-5"
              onSubmit={(event) => {
                event.preventDefault();
                void run();
              }}
            >
              <div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="font-mono text-sm font-medium">
                    {selected.path.join(" ")}
                  </h2>
                  <StatusBadge state={selected.mutability} />
                </div>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  {selected.summary}
                </p>
              </div>
              <fieldset disabled={busy} className="space-y-4">
                {selected.parameters.map((parameter) => (
                  <label className="field-label" key={parameter.name}>
                    <span>
                      {parameter.name}
                      {parameter.required ? (
                        <span className="ms-1 text-destructive">*</span>
                      ) : (
                        <span className="ms-2 text-xs font-normal text-muted-foreground">
                          {msg("registry.optional")}
                        </span>
                      )}
                    </span>
                    {parameter.value_type === "boolean" ? (
                      <input
                        className="ms-2"
                        type="checkbox"
                        checked={flags.includes(parameter.name)}
                        onChange={(event) => {
                          setFlags((current) =>
                            event.target.checked
                              ? [...current, parameter.name]
                              : current.filter(
                                  (name) => name !== parameter.name,
                                ),
                          );
                          setConfirmed(false);
                        }}
                      />
                    ) : parameter.choices?.length && !parameter.repeatable ? (
                      <select
                        className="input"
                        required={parameter.required}
                        value={values[parameter.name] ?? ""}
                        onChange={(event) => {
                          setValues((current) => ({
                            ...current,
                            [parameter.name]: event.target.value,
                          }));
                          setConfirmed(false);
                        }}
                      >
                        <option value="">
                          {parameter.required
                            ? msg("registry.choose")
                            : msg("registry.useEngineDefault")}
                        </option>
                        {parameter.choices.map((choice) => (
                          <option key={choice}>{choice}</option>
                        ))}
                      </select>
                    ) : (
                      <textarea
                        className="input font-mono font-normal"
                        required={parameter.required}
                        rows={parameter.repeatable ? 3 : 1}
                        value={values[parameter.name] ?? ""}
                        onChange={(event) => {
                          setValues((current) => ({
                            ...current,
                            [parameter.name]: event.target.value,
                          }));
                          setConfirmed(false);
                        }}
                      />
                    )}
                    <p className="field-help">
                      {parameter.summary}
                      {parameter.repeatable
                        ? msg("registry.repeatableHelp", {
                            choices: parameter.choices?.join(", ") ?? "",
                            count: parameter.choices?.length ?? 0,
                          })
                        : ""}
                    </p>
                  </label>
                ))}
              </fieldset>
              {!!selected.parameter_rules?.length && (
                <p className="text-xs leading-5 text-muted-foreground">
                  {msg(
                    "registry.theEngineAlsoChecksConditionalRequirementsBetweenTheseInputs",
                  )}
                </p>
              )}
              {selected.mutability === "apply" && (
                <label className="flex items-start gap-3 rounded-md border border-warning/40 bg-warning/5 p-3 text-sm">
                  <input
                    className="mt-1"
                    type="checkbox"
                    disabled={busy}
                    checked={confirmed}
                    onChange={(event) => setConfirmed(event.target.checked)}
                  />
                  {msg(
                    "registry.iAuthorizeThisOperationWithTheExactInputsShown",
                  )}
                </label>
              )}
              {!runnable && (
                <p className="text-sm text-muted-foreground">
                  {msg(
                    "registry.thisOperationRequiresADifferentExecutionBoundaryUseThe",
                  )}
                </p>
              )}
              <button
                className="btn-primary"
                type="submit"
                disabled={
                  busy ||
                  missing ||
                  !runnable ||
                  (selected.mutability === "apply" && !confirmed)
                }
              >
                <Play size={14} />
                {busy
                  ? msg("registry.running")
                  : selected.mutability === "read"
                    ? msg("registry.readResult")
                    : selected.mutability === "plan"
                      ? msg("registry.createPlan")
                      : msg("registry.applyOperation")}
              </button>
            </form>
          )}
          {result && (
            <section
              className="space-y-3"
              aria-label={msg("registry.operationResult")}
            >
              <ResultMeta r={result} />
              {result.ok && (
                <StatusBadge state="completed">
                  {msg("registry.operationCompleted")}
                </StatusBadge>
              )}
              {result.data && <Json v={result.data} />}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
