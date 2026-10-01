import { useState } from "react";
import { FileCheck2, ShieldAlert } from "lucide-react";
import { cliApplyConfirmed, cliPlan, type CmdResult } from "../transport";
import { Json, ResultMeta } from "../components/Result";

const ACTIONS = ["install", "update", "remove", "backup", "rollback"];
const HARNESSES = ["antigravity", "claude-code", "codex", "cursor", "grok-build", "opencode", "pi"];
const SCOPES = ["global", "project", "user_root"];

/** plan → approve(exact digest) → apply. Mirrors the CLI contract: a plan is
 *  a durable digest-bound proposal; apply executes exactly the approved
 *  operation. Timeout ⇒ "effect unconfirmed", never auto-retry. */
export default function InstallPage() {
  const [action, setAction] = useState("install");
  const [setup, setSetup] = useState("");
  const [project, setProject] = useState("");
  const [target, setTarget] = useState("");
  const [harness, setHarness] = useState("claude-code");
  const [scope, setScope] = useState("project");
  const [plan, setPlan] = useState<CmdResult | null>(null);
  const [applied, setApplied] = useState<CmdResult | null>(null);
  const [busy, setBusy] = useState<"plan" | "apply" | null>(null);

  const planData = (plan?.data ?? {}) as Record<string, unknown>;
  const operationId = String(planData.operation_id ?? "");
  const planDigest = String(planData.plan_digest ?? planData.digest ?? "");

  function planValues(): Record<string, string> {
    const v: Record<string, string> = { action };
    if (setup) v.setup = setup;
    if (project) v.project = project;
    if (scope) v.scope = scope;
    if (target) v.target = target;
    if (harness) v.harness = harness;
    return v;
  }

  async function doPlan() {
    setBusy("plan");
    setApplied(null);
    setPlan(await cliPlan("install plan", planValues()));
    setBusy(null);
  }

  async function doApply() {
    if (!operationId) return;
    setBusy("apply");
    setApplied(
      await cliApplyConfirmed("install apply", { operation: operationId }, [], true),
    );
    setBusy(null);
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="page-title">Install</h1>
        <p className="text-sm text-muted-foreground">
          Plan is a durable, digest-bound proposal. Apply executes exactly the approved operation — nothing else.
        </p>
      </header>

      <section className="grid max-w-2xl grid-cols-2 gap-3 card p-4">
        <label className="text-xs">
          Action
          <select value={action} onChange={(e) => setAction(e.target.value)}
            className="mt-1 w-full rounded-lg border border-input bg-transparent px-2 py-1.5 text-sm">
            {ACTIONS.map((a) => <option key={a}>{a}</option>)}
          </select>
        </label>
        <label className="text-xs">
          Harness
          <select value={harness} onChange={(e) => setHarness(e.target.value)}
            className="mt-1 w-full rounded-lg border border-input bg-transparent px-2 py-1.5 text-sm">
            {HARNESSES.map((h) => <option key={h}>{h}</option>)}
          </select>
        </label>
        <label className="col-span-2 text-xs">
          Setup id <span className="text-muted-foreground">(stable id from Catalog; exactly one of proposal/setup)</span>
          <input value={setup} onChange={(e) => setSetup(e.target.value)}
            placeholder="e.g. author/slug@1.2.0"
            className="mt-1 w-full rounded-lg border border-input bg-transparent px-3 py-1.5 font-mono text-sm" />
        </label>
        <label className="col-span-2 text-xs">
          Project <span className="text-muted-foreground">(required when setup is given)</span>
          <input value={project} onChange={(e) => setProject(e.target.value)}
            placeholder="/absolute/path/to/project"
            className="mt-1 w-full rounded-lg border border-input bg-transparent px-3 py-1.5 font-mono text-sm" />
        </label>
        <label className="text-xs">
          Scope
          <select value={scope} onChange={(e) => setScope(e.target.value)}
            className="mt-1 w-full rounded-lg border border-input bg-transparent px-2 py-1.5 text-sm">
            {SCOPES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label className="text-xs">
          Target <span className="text-muted-foreground">(required for project/user_root scope)</span>
          <input value={target} onChange={(e) => setTarget(e.target.value)}
            placeholder="target path or id"
            className="mt-1 w-full rounded-lg border border-input bg-transparent px-3 py-1.5 font-mono text-sm" />
        </label>
      </section>

      <button
        onClick={() => void doPlan()}
        disabled={busy !== null}
        className="btn-primary"
      >
        <FileCheck2 size={14} /> {busy === "plan" ? "Planning…" : "Create plan"}
      </button>

      {plan && (
        <section className="space-y-3 card p-4">
          <ResultMeta r={plan} />
          {plan.ok && planData && (
            <>
              <Json v={planData} />
              <div className="card border-warning/50 bg-warning/10 p-3 text-xs">
                <p className="flex items-center gap-1.5 font-semibold">
                  <ShieldAlert size={13} /> Review before applying
                </p>
                {planDigest && (
                  <p className="mt-1 font-mono">plan digest: {planDigest}</p>
                )}
                <p className="mt-1 font-mono">operation: {operationId || "—"}</p>
              </div>
              <button
                onClick={() => void doApply()}
                disabled={busy !== null || !operationId}
                className="btn-danger"
              >
                {busy === "apply" ? "Applying…" : "Apply exactly this plan"}
              </button>
            </>
          )}
        </section>
      )}

      {busy === "apply" && (
        <p className="text-xs text-muted-foreground">
          Apply is opaque up to ~120s — a timeout means “effect unconfirmed”; check status, do not retry blindly.
        </p>
      )}

      {applied && (
        <section className="space-y-2">
          <ResultMeta r={applied} />
          {applied.data && <Json v={applied.data} />}
        </section>
      )}
    </div>
  );
}
