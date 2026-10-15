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
  title = "Commands",
  description = "Explore the operations available in your native engine.",
  prefixes = [],
}: {
  title?: string;
  description?: string;
  prefixes?: string[];
}) {
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
      <PageHeader eyebrow="Tools" title={title} description={description} />
      {!help && <Spinner label="Reading available commands" />}
      {help && !help.ok && <ResultMeta r={help} />}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(250px,0.8fr)_minmax(0,1.2fr)]">
        <section
          className="card overflow-hidden"
          aria-label="Available commands"
        >
          <div className="border-b border-border p-3">
            <label className="relative block">
              <Search
                size={15}
                className="absolute left-3 top-3 text-muted-foreground"
              />
              <input
                aria-label="Filter commands"
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Find a command…"
                className="input pl-9"
              />
            </label>
          </div>
          <div className="px-4 py-2 text-xs text-muted-foreground">
            {shown.length} operations
          </div>
          <ul className="max-h-[55vh] divide-y divide-border overflow-y-auto text-sm">
            {shown.map((command) => (
              <li key={command.path.join(" ")}>
                <button
                  aria-pressed={selected === command}
                  className={`w-full p-4 text-left transition-colors hover:bg-accent ${selected === command ? "bg-primary/5" : ""}`}
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
              No matching operations.
            </p>
          )}
        </section>
        <div className="min-w-0 space-y-5">
          {!selected ? (
            <EmptyState title="Choose an operation">
              Read its description, review the accepted inputs, then run it
              here.
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
                        <span className="ml-1 text-destructive">*</span>
                      ) : (
                        <span className="ml-2 text-xs font-normal text-muted-foreground">
                          optional
                        </span>
                      )}
                    </span>
                    {parameter.value_type === "boolean" ? (
                      <input
                        className="ml-2"
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
                            ? "Choose…"
                            : "Use engine default"}
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
                        ? ` One value per line.${parameter.choices?.length ? ` Choices: ${parameter.choices.join(", ")}.` : ""}`
                        : ""}
                    </p>
                  </label>
                ))}
              </fieldset>
              {!!selected.parameter_rules?.length && (
                <p className="text-xs leading-5 text-muted-foreground">
                  The engine also checks conditional requirements between these
                  inputs.
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
                  I authorize this operation with the exact inputs shown above.
                </label>
              )}
              {!runnable && (
                <p className="text-sm text-muted-foreground">
                  This operation requires a different execution boundary. Use
                  the CLI.
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
                  ? "Running…"
                  : selected.mutability === "read"
                    ? "Read result"
                    : selected.mutability === "plan"
                      ? "Create plan"
                      : "Apply operation"}
              </button>
            </form>
          )}
          {result && (
            <section className="space-y-3" aria-label="Operation result">
              <ResultMeta r={result} />
              {result.ok && (
                <StatusBadge state="completed">Operation completed</StatusBadge>
              )}
              {result.data && <Json v={result.data} />}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
