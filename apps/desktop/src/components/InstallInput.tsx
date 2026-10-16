import type { CmdResult } from "../transport";
import { Details, ResultMeta, Spinner } from "./Result";

export interface InstallFields {
  harness: string;
  operation: string;
  setup: string;
  version: string;
  digest: string;
  targets: Record<string, string>;
  activation: string;
  executable: string;
  project: string;
}
export const emptyInstall: InstallFields = {
  harness: "",
  operation: "install",
  setup: "",
  version: "",
  digest: "",
  targets: {},
  activation: "inactive",
  executable: "",
  project: "",
};
export function installInput(fields: InstallFields): Record<string, unknown> {
  return {
    schema_version: 1,
    harness_id: fields.harness,
    operation: fields.operation,
    targets: Object.fromEntries(
      Object.entries(fields.targets).filter(([, path]) => path.trim()),
    ),
    activation: fields.activation,
    ...(fields.operation !== "remove"
      ? {
          source: {
            stable_id: fields.setup,
            version: fields.version,
            passport_digest: fields.digest,
          },
        }
      : {}),
    ...(fields.executable ? { harness_executable: fields.executable } : {}),
    ...(fields.project ? { project_root: fields.project } : {}),
  };
}
export function installComplete(fields: InstallFields) {
  return (
    !!fields.harness &&
    Object.values(fields.targets).some((path) => path.trim()) &&
    (fields.operation === "remove" ||
      !!(fields.setup.trim() && fields.version.trim() && fields.digest.trim()))
  );
}
export default function InstallInput({
  schema,
  fields,
  setFields,
}: {
  schema: CmdResult | null;
  fields: InstallFields;
  setFields: (value: InstallFields) => void;
}) {
  if (!schema) return <Spinner label="Reading accepted installation inputs" />;
  if (!schema.ok) return <ResultMeta r={schema} />;
  const properties = schema.data?.properties as
    | Record<string, { enum?: string[]; propertyNames?: { enum?: string[] } }>
    | undefined;
  const choices = (name: string) => properties?.[name]?.enum ?? [];
  const update = (name: keyof InstallFields, value: string) =>
    setFields({ ...fields, [name]: value });
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="field-label">
          Harness
          <select
            className="input"
            value={fields.harness}
            onChange={(event) => update("harness", event.target.value)}
          >
            <option value="">Choose a harness…</option>
            {choices("harness_id").map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="field-label">
          Operation
          <select
            className="input"
            value={fields.operation}
            onChange={(event) => update("operation", event.target.value)}
          >
            {choices("operation").map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
      </div>
      {fields.operation !== "remove" && (
        <fieldset className="space-y-3 rounded-md border border-border p-4">
          <legend className="px-1 text-sm font-medium">
            Exact setup version
          </legend>
          <label className="field-label">
            Setup ID
            <input
              className="input font-mono font-normal"
              value={fields.setup}
              onChange={(event) => update("setup", event.target.value)}
              placeholder="setup_…"
            />
          </label>
          <div className="grid gap-3 sm:grid-cols-[100px_1fr]">
            <label className="field-label">
              Version
              <input
                className="input font-mono font-normal"
                value={fields.version}
                onChange={(event) => update("version", event.target.value)}
                placeholder="1.0"
              />
            </label>
            <label className="field-label">
              Passport digest
              <input
                className="input font-mono font-normal"
                value={fields.digest}
                onChange={(event) => update("digest", event.target.value)}
                placeholder="sha256:…"
              />
            </label>
          </div>
          <p className="field-help">
            Use the immutable coordinates of an available setup. The engine
            validates access, trust and compatibility.
          </p>
        </fieldset>
      )}
      <fieldset className="space-y-3">
        <legend className="mb-2 text-sm font-medium">Target directories</legend>
        <p className="field-help">
          Provide an existing absolute directory for each scope you want to
          configure. Leave other scopes empty.
        </p>
        {(properties?.targets?.propertyNames?.enum ?? []).map((scope) => (
          <label className="field-label" key={scope}>
            {scope.replaceAll("_", " ")}
            <input
              className="input font-mono font-normal"
              value={fields.targets[scope] ?? ""}
              onChange={(event) =>
                setFields({
                  ...fields,
                  targets: { ...fields.targets, [scope]: event.target.value },
                })
              }
              placeholder="Absolute directory path"
            />
          </label>
        ))}
      </fieldset>
      <details className="space-y-4">
        <summary className="text-sm text-muted-foreground">
          Activation and executable
        </summary>
        <label className="field-label">
          Activation
          <select
            className="input"
            value={fields.activation}
            onChange={(event) => update("activation", event.target.value)}
          >
            {choices("activation").map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
          <p className="field-help">
            A running agent requires staged handoff and restart. The engine
            checks whether its launcher supports this.
          </p>
        </label>
        <label className="field-label">
          Installed harness executable
          <input
            className="input font-mono font-normal"
            value={fields.executable}
            onChange={(event) => update("executable", event.target.value)}
            placeholder="Optional absolute path"
          />
          <p className="field-help">
            Omit to discover the installed executable. ai-stp does not install
            or update your harness.
          </p>
        </label>
        <label className="field-label">
          Project root
          <input
            className="input font-mono font-normal"
            value={fields.project}
            onChange={(event) => update("project", event.target.value)}
            placeholder="Optional absolute project path"
          />
        </label>
      </details>
      <Details label="Exact request" value={installInput(fields)} />
    </div>
  );
}
