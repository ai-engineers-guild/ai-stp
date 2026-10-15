import { useEffect, useState } from "react";
import { cliApplyConfirmed, cliPlan, cmdMachineHelp, cmdRunRead, type CmdResult } from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";

interface Param {
  name: string;
  summary?: string;
  value_type?: string;
  required?: boolean;
  repeatable?: boolean;
  choices?: string[];
}
interface Descriptor {
  path: string[];
  summary: string;
  mutability: string;
  confirmation?: string;
  parameters?: Param[];
}

/** A process-contract client: fields, choices and effect gates come from the CLI. */
export default function RegistryPage({ title = "Commands", prefixes = [] }: { title?: string; prefixes?: string[] }) {
  const [help, setHelp] = useState<CmdResult | null>(null);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Descriptor | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [flags, setFlags] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { void cmdMachineHelp().then(setHelp); }, []);
  const commands = (help?.data?.commands ?? []) as Descriptor[];
  const shown = commands.filter((command) => {
    const path = command.path.join(" ");
    return (!prefixes.length || prefixes.some((prefix) => path === prefix || path.startsWith(`${prefix} `)))
      && (!filter || `${path} ${command.summary}`.toLowerCase().includes(filter.toLowerCase()));
  });
  const missing = selected?.parameters?.some((parameter) => parameter.required
    && (parameter.value_type === "boolean" ? !flags.includes(parameter.name) : !values[parameter.name]?.trim()));

  async function run() {
    if (!selected) return;
    setBusy(true);
    try {
      const scalar: Record<string, string> = {};
      const repeated: Record<string, string[]> = {};
      for (const parameter of selected.parameters ?? []) {
        const value = values[parameter.name];
        if (!value) continue;
        if (parameter.repeatable) repeated[parameter.name] = value.split("\n").filter(Boolean);
        else scalar[parameter.name] = value;
      }
      const path = selected.path.join(" ");
      setResult(await (selected.mutability === "read" ? cmdRunRead(path, scalar, flags, repeated)
        : selected.mutability === "plan" ? cliPlan(path, scalar, flags, repeated)
          : cliApplyConfirmed(path, scalar, flags, confirmed, repeated)));
    } finally { setBusy(false); }
  }

  return <div className="space-y-5">
    <header><h1 className="page-title">{title}</h1>
      <p className="text-sm text-muted-foreground">Operations and accepted inputs come from the connected Rust CLI.</p></header>
    <input aria-label="Filter commands" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter commands…" className="input w-full" />
    {!help && <Spinner />}
    {help && !help.ok && <ResultMeta r={help} />}
    <ul className="card divide-y divide-border text-sm">
      {shown.map((command) => <li key={command.path.join(" ")}>
        <button className="w-full p-3 text-left hover:bg-accent" disabled={busy} onClick={() => {
          setSelected(command); setValues({}); setFlags([]); setConfirmed(false); setResult(null);
        }}><span className="font-mono">{command.path.join(" ")}</span>
          <span className="ml-3 text-xs text-muted-foreground">{command.mutability}</span>
          <p className="mt-1 text-xs text-muted-foreground">{command.summary}</p></button>
      </li>)}
    </ul>
    {selected && <section className="card space-y-3 p-4">
      <h2 className="section-title">{selected.path.join(" ")}</h2>
      {(selected.parameters ?? []).map((parameter) => <label className="block space-y-1 text-sm" key={parameter.name}>
        <span>{parameter.name}{parameter.required ? " *" : ""}</span>
        {parameter.value_type === "boolean" ? <input className="ml-2" type="checkbox" checked={flags.includes(parameter.name)} onChange={(event) => {
          setFlags((current) => event.target.checked ? [...current, parameter.name] : current.filter((name) => name !== parameter.name)); setConfirmed(false);
        }} /> : parameter.choices?.length ? <select className="input block w-full" value={values[parameter.name] ?? ""} onChange={(event) => {
          setValues((current) => ({ ...current, [parameter.name]: event.target.value })); setConfirmed(false);
        }}><option value="">{parameter.required ? "Choose…" : "Default"}</option>{parameter.choices.map((choice) => <option key={choice}>{choice}</option>)}</select>
          : <textarea className="input block w-full font-mono" rows={parameter.repeatable ? 3 : 1} value={values[parameter.name] ?? ""} onChange={(event) => {
            setValues((current) => ({ ...current, [parameter.name]: event.target.value })); setConfirmed(false);
          }} />}
        <p className="text-xs text-muted-foreground">{parameter.summary}{parameter.repeatable ? " One value per line." : ""}</p>
      </label>)}
      {selected.mutability === "apply" && <label className="flex gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
        I authorize this operation with the inputs and plan digest shown above.</label>}
      <button className="btn-primary" onClick={() => void run()} disabled={busy || missing || (selected.mutability === "apply" && !confirmed)}>Run {selected.mutability}</button>
    </section>}
    {busy && <Spinner />}
    {result && <section className="space-y-2"><ResultMeta r={result} />{result.data && <Json v={result.data} />}</section>}
  </div>;
}
