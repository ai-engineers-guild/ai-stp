import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { record, records, type ContextView } from "../contexts";
import { checkoutFailure, checkoutPath } from "../checkoutLinks";
import { locationHistory, locationReceipt, locationReview, sameLocationValue, type LocationAction, type LocationEntry, type LocationReview } from "../checkoutLocation";
import { cliPlan, cmdCheckoutLocationApply, cmdMachineHelp, cmdRunRead, type CmdResult } from "../transport";
import { Details, ResultMeta, Spinner } from "./Result";

interface Props {
  original: Record<string, unknown>;
  context: ContextView | null;
  reader: string | undefined;
  disabled: boolean;
  onBusyChange: (busy: boolean) => void;
}

export default function CheckoutLocation({ original, context, reader, disabled, onBusyChange }: Props) {
  const binding = String(original.operation_id);
  const [supported, setSupported] = useState(false);
  const [entries, setEntries] = useState<LocationEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [review, setReview] = useState<LocationReview | null>(null);
  const [receipt, setReceipt] = useState<LocationReview | null>(null);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [destination, setDestination] = useState("");
  const [git, setGit] = useState("");
  const [reviewedGit, setReviewedGit] = useState<string | undefined>();
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const active = useRef(false), epoch = useRef(0);
  useLayoutEffect(() => {
    active.current = true;
    epoch.current++;
    return () => { active.current = false; epoch.current++; onBusyChange(false); };
  }, [context?.id, binding, onBusyChange]);
  function start(): number {
    setBusy(true); onBusyChange(true); setConfirmed(false);
    return ++epoch.current;
  }
  const current = (sequence: number) => active.current && sequence === epoch.current;
  function finish(sequence: number) {
    if (current(sequence)) { setBusy(false); onBusyChange(false); }
  }
  async function load(next?: string) {
    if (busy || disabled) return;
    const sequence = start();
    try {
      const help = await cmdMachineHelp();
      if (!current(sequence)) return;
      const available = [
        ["corporate project location list", "read"], ["corporate project location show", "read"],
        ["corporate project location-anchor plan", "plan"], ["corporate project location-relocate plan", "plan"],
        ["corporate project location apply", "apply"],
      ].every(([path, mutability]) => records(help.data?.commands).some((item) =>
        Array.isArray(item.path) && item.path.join(" ") === path && item.mutability === mutability));
      setSupported(available);
      if (!available) return;
      const values: Record<string, string> = { "binding-operation": binding };
      if (next) values.cursor = next;
      let response = await cmdRunRead("corporate project location list", values);
      if (!current(sequence)) return;
      const page = locationHistory(response, binding);
      if (response.ok && !page) response = checkoutFailure();
      setResult(response);
      if (page) {
        setEntries((previous) => next ? [...previous, ...page.entries.filter((entry) => !previous.some((held) => held.operation_id === entry.operation_id))] : page.entries);
        setCursor(page.cursor);
      }
    } finally { finish(sequence); }
  }
  useEffect(() => { void load(); }, []);

  async function inspect(id: string, digest?: string) {
    if (busy || disabled) return;
    const sequence = start();
    setReceipt(null);
    try {
      let response = await cmdRunRead("corporate project location show", { operation: id });
      if (!current(sequence)) return;
      const exact = locationReceipt(response.data, original);
      if (response.ok && (!exact || exact.plan.operation_id !== id || (digest !== undefined && exact.digest !== digest))) response = checkoutFailure();
      setResult(response);
      if (response.ok && exact) {
        setReceipt(exact);
        if (review?.plan.operation_id === id && review.digest === exact.digest) setReview(null);
      }
    } finally { finish(sequence); }
  }
  async function prepare(action: LocationAction) {
    if (!context || !reader || !supported || review || original.binding_retirement != null || busy || disabled) return;
    const sequence = start(), trustedGit = git.trim() ? git : undefined;
    const values: Record<string, string> = { context: reader, "binding-operation": binding };
    if (action === "relocate") values.root = destination;
    if (trustedGit) values["git-executable"] = trustedGit;
    try {
      let response = await cliPlan(`corporate project location-${action} plan`, values);
      if (!current(sequence)) return;
      const exact = locationReview(response, action, context, original, destination);
      if (response.ok && !exact) response = checkoutFailure();
      setResult(response);
      if (exact) { setReview(exact); setReviewedGit(trustedGit); }
    } finally { finish(sequence); }
  }
  async function apply() {
    if (!review || !reader || !confirmed || busy || disabled) return;
    const exact = review, sequence = start();
    try {
      let response = await cmdCheckoutLocationApply(exact.plan, exact.digest, true, reviewedGit);
      if (!current(sequence)) return;
      const retained = locationReceipt(response.data, original);
      if (response.ok && (!retained || retained.digest !== exact.digest || !sameLocationValue(retained.plan, exact.plan))) response = checkoutFailure();
      setResult(response);
      if (response.ok && retained) { setReceipt(retained); setReview(null); }
    } finally { finish(sequence); }
  }
  const locked = busy || disabled;
  return <section className="space-y-3 border-t border-border pt-4" aria-label="Checkout location">
    <h3 className="font-medium">Checkout location</h3>
    <p className="text-sm">Original adoption directory:</p>
    <p className="break-all font-mono text-xs">{checkoutPath(record(original.plan).checkout_root)}</p>
    <p className="text-sm text-muted-foreground">Location receipts record earlier reviews. Read a fresh native plan to check the present directory and company access.</p>
    <button className="btn-outline" disabled={locked} onClick={() => void load()}>Read location history</button>
    {busy && <Spinner label="Reading the original checkout location" />}
    {!busy && !supported && <p className="text-sm text-muted-foreground">This engine does not expose reviewed checkout locations.</p>}
    {result && <ResultMeta r={result} />}
    {supported && <>
      {entries.length === 0 && !busy && <p>No recorded location receipts.</p>}
      {entries.length > 0 && <ul className="space-y-2" aria-label="Recorded checkout locations">{entries.map((entry) => <li className="space-y-1" key={entry.operation_id}>
        <p className="text-sm">{entry.action === "anchor" ? "Reviewed anchor" : "Reviewed relocation"} · {entry.completed_at}</p>
        <p className="break-all font-mono text-xs">{checkoutPath(entry.root)}</p>
        <button className="btn-outline" disabled={locked} onClick={() => void inspect(entry.operation_id, entry.plan_digest)}>Inspect location {entry.operation_id}</button>
      </li>)}</ul>}
      {cursor && <button className="btn-outline" disabled={locked} onClick={() => void load(cursor)}>Read more location history</button>}
      {receipt && <div className="space-y-2" aria-label="Recorded location receipt">
        <p role="status">{receipt.action === "anchor" ? "Checkout anchor receipt saved." : "Checkout relocation receipt saved."}</p>
        <p className="text-sm">Recorded directory:</p>
        <p className="break-all font-mono text-xs">{checkoutPath(receipt.plan.destination)}</p>
        <p className="break-all font-mono text-xs">{String(receipt.plan.operation_id)} · {receipt.digest}</p>
        <Details label="Original location receipt plan" value={receipt.plan} />
      </div>}
      {original.binding_retirement == null && <>
        {!reader && <p>Select a current context for the same account and company to review a location.</p>}
        <p className="text-sm text-muted-foreground">Before moving a checkout, review and save an anchor while its registered directory is present. Then close this app and any process holding the checkout, move the same directory yourself, reopen Activity and review its new path. Copies and missing anchors require separate recovery.</p>
        <label className="field-label">Trusted Git executable for location review (optional)<input className="input" value={git} disabled={locked || !!review} onChange={(event) => setGit(event.target.value)} /></label>
        <button className="btn-outline" disabled={locked || !reader || !!review} onClick={() => void prepare("anchor")}>Review checkout anchor</button>
        <label className="field-label">Existing moved checkout directory<input className="input" value={destination} disabled={locked || !!review} onChange={(event) => setDestination(event.target.value)} /></label>
        <button className="btn-outline" disabled={locked || !reader || !!review || !destination.trim()} onClick={() => void prepare("relocate")}>Review moved checkout</button>
      </>}
      {review && <section className="space-y-3" aria-label="Review checkout location">
        <h4 className="font-medium">{review.action === "anchor" ? "Review present checkout anchor" : "Review manually moved checkout"}</h4>
        <p className="text-sm">Previously registered directory:</p>
        <p className="break-all font-mono text-xs">{checkoutPath(record(review.plan.binding).checkout_root)}</p>
        <p className="text-sm">Reviewed destination:</p>
        <p className="break-all font-mono text-xs">{checkoutPath(review.plan.destination)}</p>
        <p className="break-all font-mono text-xs">{String(review.plan.operation_id)} · {review.digest}</p>
        <Details label="Exact checkout location plan" value={review.plan} />
        <label className="flex items-start gap-3 text-sm"><input type="checkbox" checked={confirmed} disabled={locked || !reader} onChange={(event) => setConfirmed(event.target.checked)} />I reviewed this exact checkout location and authorize saving its metadata.</label>
        <button className="btn-primary" disabled={locked || !reader || !confirmed} onClick={() => void apply()}>Apply reviewed checkout location</button>
        <button className="btn-outline" disabled={locked} onClick={() => void inspect(String(review.plan.operation_id), review.digest)}>Read this location outcome</button>
        <button className="btn-outline" disabled={locked} onClick={() => { setReview(null); setConfirmed(false); }}>Close location review</button>
        <p className="text-xs text-muted-foreground">An unconfirmed reply keeps this exact plan. Read its original outcome or explicitly authorize the same plan again. After restarting, read location history before creating another review.</p>
      </section>}
    </>}
  </section>;
}
