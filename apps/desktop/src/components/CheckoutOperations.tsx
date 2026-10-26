import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { record, records, useContexts } from "../contexts";
import { checkoutFailure, checkoutReader, retainedCheckout, type CheckoutReview } from "../checkoutLinks";
import { cmdCheckoutApply, cmdMachineHelp, cmdRunRead, type CmdResult } from "../transport";
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
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [supported, setSupported] = useState(false);
  const active = useRef(false), epoch = useRef(0);
  useLayoutEffect(() => {
    active.current = true;
    epoch.current++;
    setReview(null);
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
    setConfirmed(false);
    try {
      const help = await cmdMachineHelp();
      if (!active.current || sequence !== epoch.current) return;
      const available = ["corporate project link list", "corporate project link show"].every((path) =>
        records(help?.data?.commands).some((item) => Array.isArray(item.path) && item.path.join(" ") === path && item.mutability === "read"));
      setSupported(available);
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
    setConfirmed(false);
    try {
      let response = await cmdRunRead("corporate project link show", { operation: id });
      if (!active.current || sequence !== epoch.current) return;
      const exact = retainedCheckout(response.data);
      if (response.ok && (!exact || exact.plan.operation_id !== id)) response = checkoutFailure();
      setResult(response);
      if (response.ok && exact) {
        setSelected(record(response.data));
        setReview(exact);
      }
    } finally { if (active.current && sequence === epoch.current) setBusy(false); }
  }

  const reader = review ? checkoutReader(context, contexts, review) : undefined;
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
      </div>}
    </section>
  );
}
