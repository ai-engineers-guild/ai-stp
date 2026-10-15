import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ArrowRight, Package, Search, X } from "lucide-react";
import {
  cmdCatalogSearch,
  cmdCatalogShow,
  cmdMachineHelp,
  descriptorChoices,
  type CmdResult,
} from "../transport";
import { Details, ResultMeta, Spinner } from "../components/Result";
import { EmptyState, PageHeader } from "../components/Layout";

type Item = Record<string, unknown>;
function ItemList({
  items,
  onShow,
}: {
  items: Item[];
  onShow: (id: string) => void;
}) {
  return (
    <ul className="grid gap-4 lg:grid-cols-2">
      {items.map((item) => {
        const id = String(item.stable_id);
        const trust = (item.latest_trust ?? {}) as Item;
        return (
          <li key={id}>
            <button
              onClick={() => onShow(id)}
              className="flex h-full w-full flex-col rounded-lg border border-border p-5 text-left transition-colors hover:border-primary/50 hover:bg-card"
            >
              <div className="mb-4 flex w-full items-center justify-between gap-3">
                <Package size={20} className="text-muted-foreground" />
                <span className="chip bg-muted text-muted-foreground">
                  {String(item.latest_harness_id ?? "")}
                </span>
              </div>
              <h3 className="text-sm font-medium">
                {String(item.latest_name ?? id)}
                <span className="ml-2 font-mono text-xs text-muted-foreground">
                  {String(item.latest_version ?? "")}
                </span>
              </h3>
              <p className="mt-2 line-clamp-3 text-sm leading-6 text-muted-foreground">
                {String(item.latest_description ?? "")}
              </p>
              <div className="mt-auto flex flex-wrap gap-2 pt-5">
                {trust.author_verified === true && (
                  <span className="chip bg-success/10 text-success">
                    Author verified
                  </span>
                )}
                {trust.component_verified === true && (
                  <span className="chip bg-success/10 text-success">
                    Bytes verified
                  </span>
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
  const [kinds, setKinds] = useState<string[]>([]);
  const [help, setHelp] = useState<CmdResult | null>(null);
  const [kind, setKind] = useState("setup");
  const [query, setQuery] = useState("");
  const [experimental, setExperimental] = useState(false);
  const [result, setResult] = useState<CmdResult | null>(null);
  const [detail, setDetail] = useState<CmdResult | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [expItems, setExpItems] = useState<Item[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [detailBusy, setDetailBusy] = useState(false);
  const generation = useRef(0);
  const detailGeneration = useRef(0);
  useEffect(() => {
    let active = true;
    void cmdMachineHelp().then((response) => {
      if (!active) return;
      setHelp(response);
      const choices =
        descriptorChoices(response, "registry search", "kind") ?? [];
      setKinds(choices);
      setKind((value) =>
        choices.includes(value) ? value : (choices[0] ?? ""),
      );
    });
    return () => {
      active = false;
      generation.current++;
      detailGeneration.current++;
    };
  }, []);
  function reset() {
    generation.current++;
    detailGeneration.current++;
    setBusy(false);
    setDetailBusy(false);
    setResult(null);
    setDetail(null);
    setItems([]);
    setExpItems([]);
    setCursor(null);
  }
  async function search(more = false) {
    if (!kinds.includes(kind) || busy) return;
    const request = ++generation.current;
    setBusy(true);
    detailGeneration.current++;
    setDetail(null);
    setDetailBusy(false);
    if (!more) {
      setItems([]);
      setExpItems([]);
      setCursor(null);
    }
    try {
      const response = await cmdCatalogSearch(
        kind,
        query.trim(),
        experimental,
        more ? (cursor ?? undefined) : undefined,
      );
      if (request !== generation.current) return;
      setResult(response);
      if (!response.ok) return;
      const data = response.data ?? {};
      const merge = (previous: Item[], next: Item[]) =>
        Array.from(
          new Map(
            [...previous, ...next].map((item) => [item.stable_id, item]),
          ).values(),
        );
      setItems((previous) =>
        merge(more ? previous : [], (data.items ?? []) as Item[]),
      );
      setExpItems((previous) =>
        merge(more ? previous : [], (data.experimental ?? []) as Item[]),
      );
      setCursor(typeof data.next_cursor === "string" ? data.next_cursor : null);
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }
  async function show(id: string) {
    const request = ++detailGeneration.current;
    setDetailBusy(true);
    setDetail(null);
    try {
      const response = await cmdCatalogShow(kind, id);
      if (request === detailGeneration.current) setDetail(response);
    } finally {
      if (request === detailGeneration.current) setDetailBusy(false);
    }
  }
  const summary = detail?.data?.summary as Item | undefined;
  const versions = (detail?.data?.versions ?? []) as {
    version: string;
    passport_digest: string;
    lifecycle: string;
  }[];
  return (
    <div className="page-stack">
      <PageHeader
        title="Find your next workflow"
        description="Browse setups and components published in the ai-stp catalog."
      />
      <form
        className="card flex flex-wrap items-end gap-4 p-5"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <label className="field-label">
          Show
          <select
            className="input min-w-32"
            value={kind}
            disabled={!kinds.length}
            onChange={(event) => {
              reset();
              setKind(event.target.value);
            }}
          >
            {kinds.map((value) => (
              <option key={value} value={value}>
                {value === "setup"
                  ? "Setups"
                  : value === "component"
                    ? "Components"
                    : value}
              </option>
            ))}
          </select>
        </label>
        <label className="field-label min-w-48 flex-1">
          Search
          <input
            className="input"
            maxLength={200}
            value={query}
            onChange={(event) => {
              reset();
              setQuery(event.target.value);
            }}
            placeholder="A tool, a workflow, an idea…"
          />
        </label>
        <button
          className="btn-primary h-10"
          disabled={busy || !kinds.includes(kind)}
        >
          <Search size={15} />
          Search catalog
        </button>
        <label className="flex w-full items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={experimental}
            onChange={(event) => {
              reset();
              setExperimental(event.target.checked);
            }}
          />
          Include experimental results in a separate section
        </label>
      </form>
      {help && !help.ok && <ResultMeta r={help} />}
      {busy && <Spinner label="Searching the catalog" />}
      {result && <ResultMeta r={result} />}
      {!result && !busy && (
        <EmptyState title="A starting point for your setup">
          Search for complete setups or reusable components. The engine keeps
          authoritative and experimental results separate.
        </EmptyState>
      )}
      {detailBusy && <Spinner label="Loading catalog details" />}
      {detail && (
        <section className="card space-y-5 p-5" aria-label="Catalog details">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="eyebrow">{kind} details</p>
              <h2 className="mt-2 text-lg font-medium">
                {String(summary?.latest_name ?? "Catalog item")}
              </h2>
            </div>
            <button
              className="icon-button"
              aria-label="Close details"
              onClick={() => {
                detailGeneration.current++;
                setDetail(null);
              }}
            >
              <X size={16} />
            </button>
          </div>
          <ResultMeta r={detail} />
          {summary && (
            <>
              <p className="text-sm leading-6 text-muted-foreground">
                {String(summary.latest_description ?? "")}
              </p>
              <p className="break-all font-mono text-xs text-muted-foreground">
                {String(summary.stable_id)}
              </p>
            </>
          )}
          {!!versions.length && (
            <ul className="divide-y divide-border">
              {versions.map((version) => (
                <li
                  key={version.version}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      Version {version.version}
                      <span className="ml-2 text-xs font-normal text-muted-foreground">
                        {version.lifecycle}
                      </span>
                    </p>
                    <p className="mt-1 break-all font-mono text-[10px] text-muted-foreground">
                      {version.passport_digest}
                    </p>
                  </div>
                  {kind === "setup" && version.lifecycle === "active" && (
                    <Link
                      className="btn-outline shrink-0"
                      to={`/install?${new URLSearchParams({ intent: "install", setup: String(summary?.stable_id ?? ""), version: version.version, digest: version.passport_digest, harness: String(summary?.latest_harness_id ?? "") })}`}
                    >
                      Review installation
                      <ArrowRight size={13} />
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
          {detail.data && <Details value={detail.data} />}
        </section>
      )}
      {items.length > 0 && (
        <section className="space-y-4">
          <div className="flex justify-between">
            <h2 className="section-title">Catalog results</h2>
            <p className="text-xs text-muted-foreground">
              {items.length} loaded
            </p>
          </div>
          <ItemList items={items} onShow={(id) => void show(id)} />
        </section>
      )}
      {expItems.length > 0 && (
        <section className="space-y-4">
          <h2 className="section-title">Experimental</h2>
          <ItemList items={expItems} onShow={(id) => void show(id)} />
        </section>
      )}
      {result?.ok && !items.length && !expItems.length && (
        <EmptyState title="No matching results">
          Try a different phrase or object kind.
        </EmptyState>
      )}
      {cursor && (
        <button
          className="btn-outline"
          disabled={busy}
          onClick={() => void search(true)}
        >
          Load more
        </button>
      )}
      {result?.data && <Details label="Catalog response" value={result.data} />}
    </div>
  );
}
