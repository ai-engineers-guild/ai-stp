import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import {
  cmdCatalogSearch,
  cmdCatalogShow,
  cmdMachineHelp,
  descriptorChoices,
  type CmdResult,
} from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";

// Fallback only; the live set arrives from the `registry search --kind`
// descriptor choices in machine help.
const FALLBACK_KINDS = ["component", "setup"];

type Item = Record<string, unknown>;

function ItemList({ items, onShow }: { items: Item[]; onShow: (id: string) => void }) {
  return (
    <ul className="divide-y divide-border card">
      {items.map((it, i) => {
        const id = String(it.stable_id ?? it.id ?? "");
        const trust = (it.latest_trust ?? it.trust ?? {}) as Record<string, unknown>;
        return (
          <li key={i}>
            <button
              onClick={() => onShow(id)}
              className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-accent"
            >
              <div>
                <p className="section-title">
                  {String(it.latest_name ?? it.title ?? it.name ?? id)}
                  <span className="ml-2 font-mono text-xs text-muted-foreground">
                    {String(it.latest_version ?? "")}
                  </span>
                </p>
                <p className="font-mono text-xs text-muted-foreground">{id}</p>
                {it.latest_description != null && (
                  <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                    {String(it.latest_description)}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 gap-1 text-[10px]">
                {trust.author_verified === true && (
                  <span className="chip bg-success/15 text-success">author✓</span>
                )}
                {trust.component_verified === true && (
                  <span className="chip bg-primary/15 text-primary">component✓</span>
                )}
                {trust.trust_lane != null && (
                  <span className="chip bg-muted text-muted-foreground">
                    {String(trust.trust_lane)}
                  </span>
                )}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default function CatalogPage() {
  const [kinds, setKinds] = useState<string[]>(FALLBACK_KINDS);
  const [kind, setKind] = useState("setup");
  const [query, setQuery] = useState("");
  const [experimental, setExperimental] = useState(false);
  const [res, setRes] = useState<CmdResult | null>(null);
  const [detail, setDetail] = useState<CmdResult | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [expItems, setExpItems] = useState<Item[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [detailBusy, setDetailBusy] = useState(false);

  useEffect(() => {
    void cmdMachineHelp().then((r) => {
      const choices = descriptorChoices(r, "registry search", "kind");
      if (choices) setKinds(choices);
    });
  }, []);

  async function search(more = false) {
    setBusy(true);
    try {
      const r = await cmdCatalogSearch(
        kind,
        query,
        experimental,
        more ? (cursor ?? undefined) : undefined,
      );
      setRes(r);
      const d = (r.data ?? {}) as Record<string, unknown>;
      if (!r.ok) return;
      const its = (d.items ?? d.results ?? []) as Item[];
      const exp = (d.experimental ?? []) as Item[];
      setItems((prev) => (more ? [...prev, ...its] : its));
      setExpItems((prev) => (more ? [...prev, ...exp] : exp));
      setCursor(typeof d.next_cursor === "string" ? d.next_cursor : null);
    } finally {
      setBusy(false);
    }
  }

  async function show(stableId: string) {
    setDetailBusy(true);
    try {
      setDetail(await cmdCatalogShow(kind, stableId));
    } finally {
      setDetailBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <h1 className="page-title">Catalog</h1>
        <p className="text-sm text-muted-foreground">
          Browse the registry through the CLI — private items use your CLI credentials.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded-lg border border-input bg-transparent px-2 py-1.5 text-sm"
        >
          {kinds.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void search()}
          placeholder="Search…"
          className="w-64 rounded-lg border border-input bg-transparent px-3 py-1.5 text-sm"
        />
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={experimental}
            onChange={(e) => setExperimental(e.target.checked)}
          />
          experimental
        </label>
        <button
          onClick={() => void search()}
          disabled={busy}
          className="btn-primary"
        >
          <Search size={14} /> Search
        </button>
      </div>

      {busy && <Spinner label="Querying registry" />}
      {res && <ResultMeta r={res} />}

      {items.length > 0 && <ItemList items={items} onShow={(id) => void show(id)} />}

      {expItems.length > 0 && (
        <section className="space-y-2">
          <h2 className="section-title">Experimental lane</h2>
          <p className="text-xs text-muted-foreground">
            Not authoritative — unverified community entries.
          </p>
          <ItemList items={expItems} onShow={(id) => void show(id)} />
        </section>
      )}

      {res?.ok && items.length === 0 && expItems.length === 0 && (
        <p className="text-sm text-muted-foreground">No results.</p>
      )}

      {cursor && (
        <button onClick={() => void search(true)} disabled={busy} className="btn-outline">
          Load more
        </button>
      )}

      {res?.data && (
        <details className="text-xs opacity-80">
          <summary className="cursor-pointer">Raw response</summary>
          <Json v={res.data} />
        </details>
      )}

      {detailBusy && <Spinner label="Loading detail" />}
      {detail && (
        <section className="space-y-2">
          <h2 className="section-title">Detail</h2>
          <ResultMeta r={detail} />
          {detail.data && <Json v={detail.data} />}
        </section>
      )}
    </div>
  );
}
