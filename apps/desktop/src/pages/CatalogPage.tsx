import { iconSize } from "../generated/theme";
import { useText } from "../i18n";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ArrowRight, Package, Search, X } from "lucide-react";
import {
  cmdCatalogSearch,
  cmdCatalogShow,
  cmdMachineHelp,
  cmdSetupAcquisitionPlan,
  cmdSetupAcquisitionApply,
  descriptorChoices,
  type CmdResult,
} from "../transport";
import { Details, ResultMeta, Spinner } from "../components/Result";
import { EmptyState, PageHeader } from "../components/Layout";
import { record } from "../contexts";
import { scalarText } from "../contracts";

type Item = Record<string, unknown>;
function ItemList({
  items,
  onShow,
}: {
  items: Item[];
  onShow: (id: string) => void;
}) {
  const msg = useText();
  return (
    <ul className="grid gap-4 lg:grid-cols-2">
      {items.map((item) => {
        const id = String(item.stable_id);
        const trust = (item.latest_trust ?? {}) as Item;
        return (
          <li key={id}>
            <button
              type="button"
              onClick={() => onShow(id)}
              className="flex h-full w-full flex-col rounded-lg border border-border p-5 text-start hover:border-primary/50 hover:bg-card"
            >
              <div className="mb-4 flex w-full items-center justify-between gap-3">
                <Package
                  style={iconSize.md}
                  className="text-muted-foreground"
                />
                <span className="chip bg-muted text-muted-foreground">
                  {scalarText(item.latest_harness_id ?? "")}
                </span>
              </div>
              <h3 className="text-sm font-medium">
                {scalarText(item.latest_name ?? id)}
                <span className="ms-2 font-mono text-xs text-muted-foreground">
                  {scalarText(item.latest_version ?? "")}
                </span>
              </h3>
              <p className="mt-2 line-clamp-3 text-sm leading-6 text-muted-foreground">
                {scalarText(item.latest_description ?? "")}
              </p>
              <div className="mt-auto flex flex-wrap gap-2 pt-5">
                {trust.author_verified === true && (
                  <span className="chip bg-success/10 text-success">
                    {msg("catalog.authorVerified")}
                  </span>
                )}
                {trust.component_verified === true && (
                  <span className="chip bg-success/10 text-success">
                    {msg("catalog.bytesVerified")}
                  </span>
                )}
                {trust.trust_lane != null && (
                  <span className="chip bg-muted text-muted-foreground">
                    {scalarText(trust.trust_lane)}
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
  const msg = useText();
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
  const [download, setDownload] = useState<{
    plan: Record<string, unknown>;
    digest: string;
    id: string;
    version: string;
    passport: string;
    harness: string;
    endpoint: string;
    components: number;
    complete: boolean;
  } | null>(null);
  const [downloadResult, setDownloadResult] = useState<CmdResult | null>(null);
  const [downloadApproved, setDownloadApproved] = useState(false),
    [downloadBusy, setDownloadBusy] = useState(false);
  const alive = useRef(true);
  const generation = useRef(0);
  const detailGeneration = useRef(0);
  useEffect(() => {
    let active = true;
    alive.current = true;
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
      alive.current = false;
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
  async function reviewDownload(version: {
    version: string;
    passport_digest: string;
  }) {
    const summary = record(detail?.data?.summary);
    const id = scalarText(summary.stable_id ?? ""),
      harness = scalarText(summary.latest_harness_id ?? "");
    if (!id || downloadBusy) return;
    setDownloadBusy(true);
    setDownloadApproved(false);
    try {
      const response = await cmdSetupAcquisitionPlan(id, version.version);
      if (!alive.current) return;
      const plan = record(response.data?.plan),
        operation = record(plan.operation),
        setup = record(operation.setup),
        passport = record(setup.passport);
      const digest = response.data?.plan_digest;
      if (
        response.ok &&
        operation.action === "catalog.setup.acquire" &&
        operation.access == null &&
        passport.stable_id === id &&
        passport.version === version.version &&
        setup.passport_digest === version.passport_digest &&
        typeof operation.endpoint === "string" &&
        typeof digest === "string" &&
        /^sha256:[0-9a-f]{64}$/.test(digest)
      ) {
        setDownload({
          plan,
          digest,
          id,
          version: version.version,
          passport: version.passport_digest,
          harness,
          endpoint: operation.endpoint,
          components: Object.keys(record(operation.components)).length,
          complete: false,
        });
        setDownloadResult(response);
      } else {
        setDownload(null);
        setDownloadResult(
          response.ok
            ? {
                ...response,
                ok: false,
                data: null,
                error_code: "DESKTOP_ACQUISITION_CONTRACT",
                error:
                  "The graph differs from the exact catalog selection. Read the catalog again.",
              }
            : response,
        );
      }
    } finally {
      if (alive.current) setDownloadBusy(false);
    }
  }
  async function applyDownload() {
    const held = download;
    if (!held || !downloadApproved || downloadBusy) return;
    setDownloadBusy(true);
    try {
      const response = await cmdSetupAcquisitionApply(
        held.plan,
        held.digest,
        true,
      );
      if (!alive.current) return;
      setDownloadResult(response);
      setDownloadApproved(false);
      if (response.ok) setDownload({ ...held, complete: true });
    } finally {
      if (alive.current) setDownloadBusy(false);
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
        title={msg("catalog.findYourNextWorkflow")}
        description={msg(
          "catalog.browseSetupsAndComponentsPublishedInTheAiStp",
        )}
      />
      <form
        className="card flex flex-wrap items-end gap-4 p-5"
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <label className="field-label">
          {msg("catalog.show")}
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
                  ? msg("catalog.setups")
                  : value === "component"
                    ? msg("catalog.components")
                    : value}
              </option>
            ))}
          </select>
        </label>
        <label className="field-label min-w-48 flex-1">
          {msg("catalog.search")}
          <input
            className="input"
            maxLength={200}
            value={query}
            onChange={(event) => {
              reset();
              setQuery(event.target.value);
            }}
            placeholder={msg("catalog.aToolAWorkflowAnIdea")}
          />
        </label>
        <button
          type="submit"
          className="btn-primary h-10"
          disabled={busy || !kinds.includes(kind)}
        >
          <Search style={iconSize.sm} />
          {msg("catalog.searchCatalog")}
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
          {msg("catalog.includeExperimentalResultsInASeparateSection")}
        </label>
      </form>
      {help && !help.ok && <ResultMeta r={help} />}
      {busy && <Spinner label={msg("catalog.searchingTheCatalog")} />}
      {result && <ResultMeta r={result} />}
      {!result && !busy && (
        <EmptyState title={msg("catalog.aStartingPointForYourSetup")}>
          {msg("catalog.searchForCompleteSetupsOrReusableComponentsTheEngine")}
        </EmptyState>
      )}
      {detailBusy && <Spinner label={msg("catalog.loadingCatalogDetails")} />}
      {detail && (
        <section
          className="card space-y-5 p-5"
          aria-label={msg("catalog.catalogDetails")}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="eyebrow">
                {msg("catalog.detailsOfKind", { kind })}
              </p>
              <h2 className="mt-2 text-lg font-medium">
                {scalarText(summary?.latest_name ?? msg("catalog.unnamedItem"))}
              </h2>
            </div>
            <button
              type="button"
              className="icon-button"
              aria-label={msg("catalog.closeDetails")}
              onClick={() => {
                detailGeneration.current++;
                setDetail(null);
              }}
            >
              <X style={iconSize.sm} />
            </button>
          </div>
          <ResultMeta r={detail} />
          {summary && (
            <>
              <p className="text-sm leading-6 text-muted-foreground">
                {scalarText(summary.latest_description ?? "")}
              </p>
              <p className="font-mono text-xs break-all text-muted-foreground">
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
                      {msg("catalog.version")} {version.version}
                      <span className="ms-2 text-xs font-normal text-muted-foreground">
                        {version.lifecycle}
                      </span>
                    </p>
                    <p className="mt-1 font-mono text-micro break-all text-muted-foreground">
                      {version.passport_digest}
                    </p>
                  </div>
                  {kind === "setup" && version.lifecycle === "active" && (
                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        className="btn-secondary"
                        disabled={downloadBusy}
                        onClick={() => void reviewDownload(version)}
                      >
                        {msg("catalog.downloadExactGraph")}
                      </button>
                      <Link
                        className="btn-outline shrink-0"
                        to={`/targets?${new URLSearchParams({ setup: scalarText(summary?.stable_id ?? ""), version: version.version, digest: version.passport_digest, harness: scalarText(summary?.latest_harness_id ?? "") })}`}
                      >
                        {msg("catalog.reviewLocalInstallation")}
                        <ArrowRight style={iconSize.sm} />
                      </Link>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
          {detail.data && <Details value={detail.data} />}
        </section>
      )}
      {download && (
        <section
          className="card p-5"
          aria-label={msg("catalog.exactSetupDownload")}
        >
          <h2 className="text-lg font-semibold">
            {msg("catalog.downloadExactPublicSetup")}
          </h2>
          <p className="mt-2 text-sm">
            {msg("catalog.thisSavesTheReviewedGraphInItsOriginalLocal")}
          </p>
          <p className="mt-3 text-sm break-all">
            {download.id} · {download.version}
          </p>
          <p className="mt-1 text-sm break-all text-muted-foreground">
            {download.endpoint} · {download.components}{" "}
            {msg("catalog.components2")}
          </p>
          <Details
            label={msg("catalog.exactSourceIdentity")}
            value={{
              passport_digest: download.passport,
              plan_digest: download.digest,
            }}
          />
          {!download.complete ? (
            <>
              <label className="mt-4 flex gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={downloadApproved}
                  disabled={downloadBusy}
                  onChange={(event) =>
                    setDownloadApproved(event.target.checked)
                  }
                />
                {msg("catalog.downloadThisExactGraphToTheReviewedLocalLibrary")}
              </label>
              <button
                type="button"
                className="btn-primary mt-3"
                disabled={downloadBusy || !downloadApproved}
                onClick={() => void applyDownload()}
              >
                {msg("catalog.downloadReviewedGraph")}
              </button>
            </>
          ) : (
            <Link
              className="btn-primary mt-4"
              to={
                "/targets?" +
                new URLSearchParams({
                  setup: download.id,
                  version: download.version,
                  digest: download.passport,
                  harness: download.harness,
                })
              }
            >
              {msg("catalog.configureDownloadedSetup")}
            </Link>
          )}
        </section>
      )}
      {downloadBusy && (
        <Spinner label={msg("catalog.checkingTheExactPublicSetupGraph")} />
      )}
      {downloadResult && <ResultMeta r={downloadResult} />}
      {items.length > 0 && (
        <section className="space-y-4">
          <div className="flex justify-between">
            <h2 className="section-title">{msg("catalog.catalogResults")}</h2>
            <p className="text-xs text-muted-foreground">
              {items.length} {msg("catalog.loaded")}
            </p>
          </div>
          <ItemList items={items} onShow={(id) => void show(id)} />
        </section>
      )}
      {expItems.length > 0 && (
        <section className="space-y-4">
          <h2 className="section-title">{msg("catalog.experimental")}</h2>
          <ItemList items={expItems} onShow={(id) => void show(id)} />
        </section>
      )}
      {result?.ok && !items.length && !expItems.length && (
        <EmptyState title={msg("catalog.noMatchingResults")}>
          {msg("catalog.tryADifferentPhraseOrObjectKind")}
        </EmptyState>
      )}
      {cursor && (
        <button
          type="button"
          className="btn-outline"
          disabled={busy}
          onClick={() => void search(true)}
        >
          {msg("catalog.loadMore")}
        </button>
      )}
      {result?.data && (
        <Details label={msg("catalog.catalogResponse")} value={result.data} />
      )}
    </div>
  );
}
