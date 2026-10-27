import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { record, records, useContexts } from "../contexts";
import { checkoutFailure, checkoutPath, checkoutReader, checkoutReceipt, checkoutReview, retainedCheckout, type CheckoutReview } from "../checkoutLinks";
import { bindingRetirementReceipt, bindingRetirementReview, type BindingRetirementReview } from "../bindingRetirement";
import { cliPlan, cmdBindingRetirementApply, cmdCheckoutApply, cmdMachineHelp, cmdRunRead, type CmdResult } from "../transport";
import { Details, ResultMeta, Spinner } from "./Result";

export default function CheckoutOperations() {
  const context = useContexts((state) => state.selected);
  const contexts = useContexts((state) => state.result);
  const switching = useContexts((state) => state.loading || state.switching);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [review, setReview] = useState<CheckoutReview | null>(null);
  const [nextReview, setNextReview] = useState<CheckoutReview | null>(null);
  const [retirement, setRetirement] = useState<BindingRetirementReview | null>(null);
  const [root, setRoot] = useState("");
  const [git, setGit] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [supported, setSupported] = useState(false);
  const [retirementSupported, setRetirementSupported] = useState(false);
  const active = useRef(false), epoch = useRef(0);
  useLayoutEffect(() => {
    active.current = true;
    epoch.current++;
    setReview(null);
    setNextReview(null);
    setRetirement(null);
    setSelected(null);
    setConfirmed(false);
    setResult(null);
    setBusy(false);
    return () => { active.current = false; epoch.current++; };
  }, [context?.id]);

  async function load(next?: string) {
    if (busy || switching) return;
    const sequence = ++epoch.current;
    setBusy(true);
    setReview(null);
    setNextReview(null);
    setRetirement(null);
    setConfirmed(false);
    try {
      const help = await cmdMachineHelp();
      if (!active.current || sequence !== epoch.current) return;
      const available = ["corporate project link list", "corporate project link show"].every((path) =>
        records(help?.data?.commands).some((item) => Array.isArray(item.path) && item.path.join(" ") === path && item.mutability === "read"));
      setSupported(available);
      setRetirementSupported(["corporate project binding-retire plan", "corporate project binding-retire apply"].every((path, index) =>
        records(help?.data?.commands).some((item) => Array.isArray(item.path) && item.path.join(" ") === path && item.mutability === (index === 0 ? "plan" : "apply"))));
      if (!available) { setRows([]); return; }
      const values: Record<string, string> = { limit: "50" };
      if (next) values.cursor = next;
      let response = await cmdRunRead("corporate project link list", values);
      if (!active.current || sequence !== epoch.current) return;
      const items = records(response.data?.items);
      if (response.ok && (!Array.isArray(response.data?.items) || items.length > 50 || items.some((item) => !retainedCheckout(item)))) response = checkoutFailure();
      setResult(response);
      if (response.ok) {
        setRows((previous) => next ? [...previous, ...items.filter((item) => !previous.some((held) => held.operation_id === item.operation_id))] : items);
        setCursor(typeof response.data?.next_cursor === "string" ? response.data.next_cursor : null);
      }
    } finally { if (active.current && sequence === epoch.current) setBusy(false); }
  }
  useEffect(() => { void load(); }, []);

  async function inspect(id: string) {
    if (busy || switching) return;
    const sequence = ++epoch.current;
    setBusy(true);
    setReview(null);
    setNextReview(null);
    setRetirement(null);
    setConfirmed(false);
    try {
      let response = await cmdRunRead("corporate project link show", { operation: id });
      if (!active.current || sequence !== epoch.current) return;
      const exact = retainedCheckout(response.data);
      if (response.ok && (!exact || exact.plan.operation_id !== id)) response = checkoutFailure();
      if (response.ok && exact?.action === "adopt" && response.data?.binding_retirement != null &&
        !bindingRetirementReceipt(response.data.binding_retirement, record(response.data))) response = checkoutFailure();
      setResult(response);
      if (response.ok && exact) {
        setSelected(record(response.data));
        setReview(exact);
        setRoot(checkoutPath(exact.plan.checkout_root) ?? "");
        setGit("");
      }
    } finally { if (active.current && sequence === epoch.current) setBusy(false); }
  }

  const reader = review ? checkoutReader(context, contexts, review) : undefined;
  async function prepareRetirement() {
    if (!selected || !review || review.action !== "adopt" || selected.state !== "completed" ||
      !reader || !context || !retirementSupported || retirement || selected.binding_retirement !== null || busy || switching) return;
    const original = selected, sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      let response = await cliPlan("corporate project binding-retire plan", {
        context: reader, "binding-operation": String(review.plan.operation_id),
      });
      if (!active.current || sequence !== epoch.current) return;
      const exact = bindingRetirementReview(response, context, original);
      if (response.ok && !exact) response = checkoutFailure();
      setResult(response);
      if (exact) setRetirement(exact);
    } finally { if (active.current && sequence === epoch.current) setBusy(false); }
  }

  async function applyRetirement() {
    if (!retirement || !selected || !reader || !confirmed || busy || switching) return;
    const exact = retirement, original = selected, sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      let response = await cmdBindingRetirementApply(exact.plan, exact.digest, true);
      if (!active.current || sequence !== epoch.current) return;
      if (response.ok && (!bindingRetirementReceipt(response.data, original) ||
        response.data?.plan_digest !== exact.digest || response.data?.operation_id !== exact.plan.operation_id)) response = checkoutFailure();
      setResult(response);
      if (response.ok) { setSelected({ ...original, binding_retirement: response.data }); setRetirement(null); }
    } finally { if (active.current && sequence === epoch.current) setBusy(false); }
  }
  async function prepare(action: "confirm" | "adopt") {
    if (!review || !reader || !context || nextReview || busy || switching) return;
    const source = review, snapshot = record(record(source.plan.change).snapshot);
    const request = source.action === "request" ? source.plan.operation_id : record(source.plan.change).request_operation_id;
    if (typeof request !== "string" || (action === "confirm" && record(snapshot.context).context_id !== context.id)) return;
    const sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      const values: Record<string, string> = { "request-operation": request };
      if (action === "adopt") { values.context = reader; values.root = root; }
      if (git.trim()) values["git-executable"] = git;
      let response = await cliPlan(`corporate project link-${action} plan`, values);
      if (!active.current || sequence !== epoch.current) return;
      const exact = checkoutReview(response, action, context, String(record(snapshot.target).remote_project_id), snapshot, request);
      if (response.ok && !exact) response = checkoutFailure();
      setResult(response);
      if (exact) setNextReview(exact);
    } finally { if (active.current && sequence === epoch.current) setBusy(false); }
  }

  async function applyNext() {
    if (!nextReview || !reader || !confirmed || busy || switching) return;
    const exact = nextReview, sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      let response = await cmdCheckoutApply(exact.plan, exact.digest, true, reader, git.trim() ? git : undefined);
      if (!active.current || sequence !== epoch.current) return;
      if (response.ok && !checkoutReceipt(response, exact)) response = checkoutFailure();
      setResult(response);
      if (response.ok) { setSelected(record(response.data)); setReview(exact); setNextReview(null); }
    } finally { if (active.current && sequence === epoch.current) setBusy(false); }
  }
  async function reconcile() {
    if (!review || !reader || !confirmed || busy || switching) return;
    const exact = review, sequence = ++epoch.current;
    setBusy(true);
    setConfirmed(false);
    try {
      let response = await cmdCheckoutApply(exact.plan, exact.digest, true, reader);
      if (!active.current || sequence !== epoch.current) return;
      if (response.ok && (!retainedCheckout(response.data) || response.data?.operation_id !== exact.plan.operation_id || response.data?.plan_digest !== exact.digest)) response = checkoutFailure();
      setResult(response);
      if (response.ok) setSelected(record(response.data));
    } finally { if (active.current && sequence === epoch.current) setBusy(false); }
  }

  return (
    <section className="card space-y-4 p-5" aria-label="Corporate checkout history">
      <h2 className="section-title">Corporate checkout operations</h2>
      <p className="text-sm text-muted-foreground">Original requests and confirmations across saved views stay in the native journal, including after restarting the app.</p>
      <button className="btn-outline" disabled={busy || switching} onClick={() => void load()}>Read checkout history</button>
      {busy && <Spinner label="Reading the original checkout operation" />}
      {!busy && !supported && <p className="text-sm text-muted-foreground">This engine does not expose checkout history.</p>}
      {supported && rows.length === 0 && !busy && <p>No retained checkout operations.</p>}
      {rows.length > 0 && <ul className="divide-y divide-border">{rows.map((item) => {
        const snapshot = record(record(record(item.plan).change).snapshot);
        return <li className="space-y-2 py-3" key={String(item.operation_id)}>
          <p className="text-sm font-medium">{String(record(snapshot.context).label ?? "Original context")} · {String(item.state)}</p>
          <p className="break-all text-xs text-muted-foreground">{String(record(snapshot.account).origin ?? "")} · {String(record(snapshot.target).remote_project_id ?? "")}</p>
          <button className="btn-outline" disabled={busy || switching} onClick={() => void inspect(String(item.operation_id))}>Inspect {String(item.operation_id)}</button>
        </li>;
      })}</ul>}
      {cursor && <button className="btn-outline" disabled={busy || switching} onClick={() => void load(cursor)}>Read more checkout history</button>}
      {result && <ResultMeta r={result} />}
      {review && selected && <div className="space-y-3" aria-label="Original checkout operation">
        <p className="break-all font-mono text-xs">{String(review.plan.operation_id)} · {review.digest}</p>
        <Details label="Original checkout journal" value={selected} />
        {["applying", "interrupted"].includes(String(selected.state)) && <>
          <p className="text-sm text-muted-foreground">Reconciliation reads the original outcome through a matching current company context. An absent result stays unknown.</p>
          {!reader && <p>Select a current context for the same account and company to read this original outcome.</p>}
          <label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={confirmed} disabled={!reader || busy || switching} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed this original intent and authorize outcome reconciliation.</label>
          <button className="btn-primary" disabled={!reader || !confirmed || busy || switching} onClick={() => void reconcile()}>Reconcile original outcome</button>
        </>}
        {selected.state === "completed" && review.action !== "adopt" && !nextReview && <div className="space-y-3">
          <p className="text-sm text-muted-foreground">Continue the original request with a fresh native review. The engine checks the current server link before any new change.</p>
          <label className="field-label">Registered checkout for binding<input className="input" value={root} disabled={busy || switching} onChange={(event) => setRoot(event.target.value)} /></label>
          <label className="field-label">Trusted Git executable for checkout review (optional)<input className="input" value={git} disabled={busy || switching} onChange={(event) => setGit(event.target.value)} /></label>
          {review.action === "request" && <button className="btn-outline" disabled={!reader || busy || switching || record(record(record(review.plan.change).snapshot).context).context_id !== context?.id} onClick={() => void prepare("confirm")}>Review original confirmation</button>}
          <button className="btn-outline" disabled={!reader || !root.trim() || busy || switching} onClick={() => void prepare("adopt")}>Review original local binding</button>
        </div>}
        {selected.state === "completed" && review.action === "adopt" && <div className="space-y-3">
          {selected.binding_retirement != null ? <>
            <p role="status">This original local binding was retired. Its adoption receipt is preserved.</p>
            <Details label="Verified local binding retirement" value={selected.binding_retirement} />
          </> : <>
            <p role="status">Original corporate project binding receipt saved.</p>
            {retirementSupported && selected.binding_retirement === null && !retirement && <>
              <p className="text-sm text-muted-foreground">After this exact link is unlinked on the server, review releasing its local reservation. Checkout files, tasks and harness configuration are preserved.</p>
              <button className="btn-outline" disabled={!reader || busy || switching} onClick={() => void prepareRetirement()}>Review local binding retirement</button>
            </>}
          </>}
          {retirement && <div className="space-y-3" aria-label="Review local binding retirement">
            <h3 className="font-medium">Release only this original local binding</h3>
            <p className="text-sm text-muted-foreground">The CLI observed the exact server link as unlinked. Applying rechecks current rights and local state. It does not unlink another link or change checkout files, tasks or harness configuration.</p>
            <p className="break-all font-mono text-xs">{retirement.digest}</p>
            <Details label="Exact local binding retirement plan" value={retirement.plan} />
            <label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={confirmed} disabled={!reader || busy || switching} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed this exact local binding retirement and authorize releasing its reservation.</label>
            <button className="btn-primary" disabled={!reader || !confirmed || busy || switching} onClick={() => void applyRetirement()}>Apply reviewed local binding retirement</button>
            <p className="text-xs text-muted-foreground">If the reply is unconfirmed, inspect this original operation in Activity. An explicit retry retains this exact plan and operation.</p>
          </div>}
        </div>}
        {nextReview && <div className="space-y-3" aria-label="Review retained checkout next change">
          <h3 className="font-medium">Review original {nextReview.action === "confirm" ? "confirmation" : "local binding"}</h3>
          <p className="break-all font-mono text-xs">{nextReview.digest}</p>
          <Details label="Exact retained checkout next plan" value={nextReview.plan} />
          <label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={confirmed} disabled={!reader || busy || switching} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed this exact retained checkout change and authorize it.</label>
          <button className="btn-primary" disabled={!reader || !confirmed || busy || switching} onClick={() => void applyNext()}>Apply reviewed original checkout change</button>
        </div>}
      </div>}
    </section>
  );
}
