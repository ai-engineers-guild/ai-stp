import { useLayoutEffect, useRef, useState } from "react";
import { record, records, type ContextView } from "../contexts";
import { cliPlan, type CmdResult } from "../transport";
import { Details, ResultMeta, Spinner } from "./Result";

function refused(): CmdResult {
  return {
    ok: false,
    data: null,
    warnings: [],
    continuations: [],
    error:
      "The checkout preview does not match this company and project. Read it again.",
    error_code: "CONTEXT_VIEW",
  };
}

export default function CheckoutPreview({
  context,
  project,
  disabled,
}: {
  context: ContextView;
  project: { id: string; name: string };
  disabled: boolean;
}) {
  const [root, setRoot] = useState("");
  const [git, setGit] = useState("");
  const [provider, setProvider] = useState("");
  const [providers, setProviders] = useState<Record<string, unknown>[]>([]);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState(false);
  const epoch = useRef(0);
  const active = useRef(false);
  useLayoutEffect(() => {
    active.current = true;
    epoch.current++;
    return () => {
      active.current = false;
      epoch.current++;
    };
  }, []);

  async function preview() {
    if (disabled || busy || context.mode !== "corporate" || !root.trim())
      return;
    const sequence = ++epoch.current;
    const values: Record<string, string> = {
      context: context.id,
      project: project.id,
      root,
    };
    if (git.trim()) values["git-executable"] = git;
    if (provider) values["provider-project"] = provider;
    setBusy(true);
    setResult(null);
    try {
      let response = await cliPlan("corporate project link-preview", values);
      if (!active.current || sequence !== epoch.current) return;
      const data = record(response.data?.preview);
      const target = record(data.target);
      const account = record(data.account);
      const authority = record(record(data.context).authority);
      if (
        response.ok &&
        (record(data.context).context_id !== context.id ||
          account.origin !== context.origin ||
          (record(account.connection).connection_id ?? null) !==
            context.connection ||
          target.remote_project_id !== project.id ||
          record(data.request_coordinates).remote_project_id !== project.id ||
          record(data.request_coordinates).provider_project_id !==
            (provider || null) ||
          (record(data.selected_provider).provider_project_id ?? null) !==
            (provider || null) ||
          target.organization_id !==
            record(authority.organization).organization_id ||
          data.observation_only !== true ||
          data.online_verified !== true ||
          data.link_created !== false ||
          data.binding_created !== false ||
          data.request_admitted !== false ||
          data.installation_authority !== false)
      )
        response = refused();
      setResult(response);
      // These are choices for a new checked preview, never a cached grant.
      if (response.ok) setProviders(records(target.providers));
      else {
        setProviders([]);
        setProvider("");
      }
    } finally {
      if (active.current && sequence === epoch.current) setBusy(false);
    }
  }

  const data = record(result?.data?.preview);
  const checkout = record(record(data.checkout).checkout);
  const local = record(data.local_project);
  const observedRoot = record(local.root).path;
  return (
    <section className="card space-y-4" aria-label="Corporate checkout preview">
      <div className="space-y-2">
        <h2 className="section-title">Review checkout for {project.name}</h2>
        <p className="text-sm text-muted-foreground">
          Choose an existing registered project with a committed Git branch. The
          engine checks its private passport and current company access.
        </p>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void preview();
        }}
      >
        <fieldset disabled={busy || disabled} className="space-y-4">
          <label className="field-label">
            Checkout directory
            <input
              className="input"
              required
              value={root}
              onChange={(event) => {
                setRoot(event.target.value);
                setResult(null);
                setProviders([]);
                setProvider("");
              }}
            />
          </label>
          <label className="field-label">
            Git executable (optional)
            <input
              className="input"
              value={git}
              onChange={(event) => {
                setGit(event.target.value);
                setResult(null);
                setProviders([]);
                setProvider("");
              }}
            />
          </label>
          <p className="field-help">
            Use an absolute path to an existing trusted Git executable if
            needed. The engine uses your installed Git and does not download
            one.
          </p>
          {providers.length > 0 && (
            <label className="field-label">
              Corporate repository (optional)
              <select
                className="input"
                value={provider}
                onChange={(event) => {
                  setProvider(event.target.value);
                  setResult(null);
                }}
              >
                <option value="">No repository assertion</option>
                {providers.map((item) => (
                  <option
                    key={String(item.provider_project_id)}
                    value={String(item.provider_project_id)}
                  >
                    {String(item.provider)} · repository{" "}
                    {String(item.immutable_repository_id)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button className="btn-primary" type="submit" disabled={!root.trim()}>
            Preview checkout
          </button>
        </fieldset>
      </form>
      {busy && <Spinner label="Checking checkout and current company access" />}
      {result && <ResultMeta r={result} />}
      {result?.ok && (
        <div className="space-y-3" aria-label="Verified checkout observation">
          <h3 className="font-medium">Checkout verified for review</h3>
          {typeof observedRoot === "string" && (
            <p className="break-all text-sm">{observedRoot}</p>
          )}
          <p className="break-all font-mono text-xs text-muted-foreground">
            Commit {String(checkout.commit ?? "")}
          </p>
          <p className="text-sm text-muted-foreground">
            Preview only. Saving a project link requires a separate reviewed
            operation. Repository choices come from the company; Git addresses
            do not prove repository identity.
          </p>
          <Details label="Checkout observation evidence" value={result.data} />
        </div>
      )}
    </section>
  );
}
