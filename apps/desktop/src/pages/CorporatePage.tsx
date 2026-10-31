import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { Building2, RefreshCw } from "lucide-react";
import { record, records, useContexts } from "../contexts";
import {
  cliPlan,
  cmdMachineHelp,
  cmdRunRead,
  descriptorChoices,
  type CmdResult,
} from "../transport";
import { EmptyState, PageHeader } from "../components/Layout";
import { Details, ResultMeta, Spinner } from "../components/Result";
import CheckoutPreview from "../components/CheckoutPreview";
import HeartbeatDelivery from "../components/HeartbeatDelivery";

const TABS = [
  "Projects",
  "Teams",
  "Technologies",
  "Mappings",
  "Catalog",
  "Assignments",
  "Heartbeat",
] as const;
type Tab = (typeof TABS)[number];

export default function CorporatePage() {
  const context = useContexts((state) => state.selected);
  const contextLoading = useContexts(
    (state) => state.loading || state.switching,
  );
  const [tab, setTab] = useState<Tab>("Projects");
  const [result, setResult] = useState<CmdResult | null>(null);
  const [help, setHelp] = useState<CmdResult | null>(null);
  const [harnesses, setHarnesses] = useState<string[]>([]);
  const [harness, setHarness] = useState("");
  const [kind, setKind] = useState("setup");
  const [query, setQuery] = useState("");
  const [membershipOnly, setMembershipOnly] = useState(true);
  const [projects, setProjects] = useState<Record<string, unknown>[]>([]);
  const [technologies, setTechnologies] = useState<Record<string, unknown>[]>(
    [],
  );
  const [project, setProject] = useState("");
  const [technology, setTechnology] = useState("");
  const [checkoutProject, setCheckoutProject] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [heartbeatView, setHeartbeatView] = useState<"policy" | "status">("policy");
  const heartbeatPath = `corporate heartbeat ${heartbeatView}`;
  const heartbeatSupported = help?.ok === true && records(help.data?.commands).some(
    (command) => Array.isArray(command.path) && command.path.join(" ") === heartbeatPath &&
      command.mutability === "read",
  );
  const epoch = useRef(0);
  const request = useRef(0);
  const active = useRef(false);
  useLayoutEffect(() => {
    active.current = true;
    epoch.current++;
    request.current++;
    setResult(null);
    setBusy(false);
    setQuery("");
    setProject("");
    setTechnology("");
    setProjects([]);
    setTechnologies([]);
    setCheckoutProject(null);
    setHeartbeatView("policy");
    return () => {
      active.current = false;
      epoch.current++;
      request.current++;
    };
  }, [context?.id]);
  useEffect(() => {
    let mounted = true;
    void cmdMachineHelp().then((response) => {
      if (!mounted) return;
      setHelp(response);
      const choices =
        descriptorChoices(
          response,
          "corporate assignments preview",
          "harness",
        ) ?? [];
      setHarnesses(choices);
      setHarness(choices[0] ?? "");
    });
    return () => {
      mounted = false;
    };
  }, []);
  function invalidate() {
    request.current++;
    setResult(null);
    setBusy(false);
  }
  async function read(
    mapping?: string,
    page: { cursor?: string; offset?: number } = {},
  ) {
    if (!context || context.mode !== "corporate" || contextLoading || busy)
      return;
    if (tab === "Heartbeat" && !heartbeatSupported) return;
    const view = context.id,
      viewEpoch = epoch.current,
      sequence = ++request.current;
    const values: Record<string, string> = { context: view };
    let path: string,
      flags: string[] = [];
    if (mapping) {
      path = "corporate mappings show";
      values.version = mapping;
    } else
      switch (tab) {
        case "Projects":
          path = "corporate projects";
          if (membershipOnly) flags = ["membership-only"];
          break;
        case "Teams":
          path = "corporate teams";
          break;
        case "Heartbeat":
          path = heartbeatPath;
          break;
        case "Technologies":
          path = "corporate technologies";
          if (query.trim()) values.query = query.trim();
          if (page.offset !== undefined) values.offset = String(page.offset);
          break;
        case "Mappings":
          path = "corporate mappings list";
          break;
        case "Catalog":
          path = "corporate catalog search";
          values.kind = kind;
          if (query.trim()) values.query = query.trim();
          if (harness) values.harness = harness;
          if (page.cursor) values.cursor = page.cursor;
          break;
        case "Assignments":
          path = "corporate assignments preview";
          values.harness = harness;
          if (project) values.project = project;
          if (technology) values.technology = technology;
          break;
      }
    setBusy(true);
    setResult(null);
    try {
      let response =
        tab === "Assignments" && !mapping
          ? await cliPlan(path, values)
          : await cmdRunRead(path, values, flags);
      if (
        !active.current ||
        epoch.current !== viewEpoch ||
        request.current !== sequence
      )
        return;
      const observation = record(response.data?.observation);
      if (response.ok && record(observation.context).context_id !== view) {
        response = {
          ok: false,
          data: null,
          warnings: [],
          continuations: [],
          error:
            "The response belongs to a different context. Read this view again.",
          error_code: "CONTEXT_VIEW",
        };
      }
      setResult(response);
      if (response.ok) {
        const items = records(record(observation.data).items);
        if (tab === "Projects") setProjects(items);
        if (tab === "Technologies") setTechnologies(items);
      }
    } finally {
      if (
        active.current &&
        epoch.current === viewEpoch &&
        request.current === sequence
      )
        setBusy(false);
    }
  }
  const observation = record(result?.data?.observation),
    data = record(observation.data);
  const rows = records(Array.isArray(data.items) ? data.items : data.entries);
  const permissions = record(record(observation.observation).capabilities);
  const observedRequest = record(observation.request);
  const mapping = observedRequest.action === "mapping";
  const cursor = record(data.page).next_cursor;
  const nextCursor =
    tab === "Catalog" &&
    observedRequest.action === "catalog" &&
    typeof cursor === "string" &&
    cursor.length > 0
      ? cursor
      : null;
  const offset =
    typeof observedRequest.offset === "number" ? observedRequest.offset : 0;
  const nextOffset =
    tab === "Technologies" &&
    observedRequest.action === "technologies" &&
    rows.length > 0 &&
    typeof data.total === "number" &&
    offset + rows.length < data.total &&
    offset + rows.length <= 1_000_000
      ? offset + rows.length
      : null;
  const unavailable =
    help?.ok === false ||
    (help?.ok === true && (tab === "Heartbeat" ? !heartbeatSupported : !harnesses.length));
  const checkoutSupported = records(help?.data?.commands).some(
    (command) =>
      Array.isArray(command.path) &&
      command.path.join(" ") === "corporate project link-preview" &&
      command.mutability === "plan",
  );
  const checkoutLinking = [
    ["corporate project link-request plan", "plan"],
    ["corporate project link-confirm plan", "plan"],
    ["corporate project link-adopt plan", "plan"],
    ["corporate project link apply", "apply"],
  ].every(([path, mutability]) => records(help?.data?.commands).some((command) =>
    Array.isArray(command.path) && command.path.join(" ") === path && command.mutability === mutability,
  ));
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Corporate"
        title={context?.organization ?? "Company hub"}
        description="Read your company's projects, people, technology mappings and setup assignments through the selected connection."
        action={
          <Building2
            size={26}
            className="text-muted-foreground"
            aria-hidden="true"
          />
        }
      />
      {contextLoading && <Spinner label="Reading the selected context" />}
      {context?.mode !== "corporate" ? (
        <EmptyState
          title="Select a corporate context"
          action={
            <Link className="btn-primary" to="/profiles">
              Manage connections and contexts
            </Link>
          }
        >
          Personal use works without a company account. A company context gives
          you access to your team's authorized directory and assignments.
        </EmptyState>
      ) : (
        <>
          <div className="card space-y-1 text-sm">
            <p className="font-medium">{context.label}</p>
            <p className="break-all text-xs text-muted-foreground">
              {context.origin}
            </p>
            <p className="text-xs text-muted-foreground">
              Current permissions are checked on every read. Saved views do not
              grant installation access.
            </p>
          </div>
          <div
            className="flex flex-wrap gap-2"
            role="group"
            aria-label="Company information"
          >
            {TABS.map((value) => (
              <button
                className={tab === value ? "btn-primary" : "btn-outline"}
                key={value}
                aria-pressed={tab === value}
                onClick={() => {
                  invalidate();
                  setTab(value);
                  setQuery("");
                  setCheckoutProject(null);
                }}
              >
                {value}
              </button>
            ))}
          </div>
          {unavailable && (
            <EmptyState title={tab === "Heartbeat"
              ? "This engine does not advertise this heartbeat read"
              : "This engine does not advertise company reads"}>
              Use a matching CLI and desktop release to open these views.
            </EmptyState>
          )}
          <form
            className="card space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              void read();
            }}
          >
            <div className="grid gap-4 md:grid-cols-2">
              {tab === "Heartbeat" && (
                <label className="field-label">
                  Heartbeat view
                  <select className="input" value={heartbeatView} onChange={(event) => {
                    invalidate();
                    setHeartbeatView(event.target.value as "policy" | "status");
                  }}>
                    <option value="policy">Reporting policy</option>
                    <option value="status">Enrolled device status</option>
                  </select>
                </label>
              )}
              {tab === "Projects" && (
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={membershipOnly}
                    onChange={(event) => {
                      invalidate();
                      setMembershipOnly(event.target.checked);
                    }}
                  />
                  Only projects I belong to
                </label>
              )}
              {(tab === "Technologies" || tab === "Catalog") && (
                <label className="field-label">
                  Search
                  <input
                    className="input"
                    maxLength={200}
                    value={query}
                    onChange={(event) => {
                      invalidate();
                      setQuery(event.target.value);
                    }}
                  />
                </label>
              )}
              {tab === "Catalog" && (
                <label className="field-label">
                  Object kind
                  <select
                    className="input"
                    value={kind}
                    onChange={(event) => {
                      invalidate();
                      setKind(event.target.value);
                    }}
                  >
                    <option value="setup">Setups</option>
                    <option value="component">Components</option>
                  </select>
                </label>
              )}
              {(tab === "Catalog" || tab === "Assignments") && (
                <label className="field-label">
                  Harness
                  <select
                    className="input"
                    value={harness}
                    disabled={!harnesses.length}
                    onChange={(event) => {
                      invalidate();
                      setHarness(event.target.value);
                    }}
                  >
                    {!harnesses.length && (
                      <option value="">Reading engine support…</option>
                    )}
                    {harnesses.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {tab === "Assignments" && (
                <>
                  <label className="field-label">
                    Corporate project
                    <select
                      className="input"
                      value={project}
                      onChange={(event) => {
                        invalidate();
                        setProject(event.target.value);
                      }}
                    >
                      <option value="">Organization context</option>
                      {projects.map((item) => (
                        <option
                          key={String(item.project_id)}
                          value={String(item.project_id)}
                        >
                          {String(item.name)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field-label">
                    Technology
                    <select
                      className="input"
                      value={technology}
                      onChange={(event) => {
                        invalidate();
                        setTechnology(event.target.value);
                      }}
                    >
                      <option value="">No technology filter</option>
                      {technologies.map((item) => (
                        <option
                          key={String(item.technology_id)}
                          value={String(item.technology_id)}
                        >
                          {String(item.name)}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              )}
            </div>
            {tab === "Projects" && (
              <p className="text-xs text-muted-foreground">
                Visible projects and explicit memberships are separate.
                Assignment planning may require project membership.
              </p>
            )}
            {tab === "Assignments" && (
              <p className="text-sm text-muted-foreground">
                Preview starts with an empty company-managed inventory. It does
                not report personal installations or change harness files. Read
                Projects or Technologies to choose a scope.
              </p>
            )}
            {tab === "Heartbeat" && (
              <><p className="text-sm text-muted-foreground">
                Reading these views does not enable reporting. Company policy
                is separate from your consent. Device health does not establish
                harness usage.
              </p><HeartbeatDelivery key={context.id} context={context} help={help} disabled={contextLoading} /></>
            )}
            <button
              className="btn-primary"
              disabled={
                busy ||
                contextLoading ||
                unavailable ||
                !help ||
                (tab === "Assignments" && !harness)
              }
              type="submit"
            >
              <RefreshCw size={15} aria-hidden="true" />
              {tab === "Assignments"
                ? "Preview assignments"
                : tab === "Heartbeat" ? `Read heartbeat ${heartbeatView}`
                : `Read ${tab.toLowerCase()}`}
            </button>
          </form>
          {checkoutProject && checkoutSupported && (
            <CheckoutPreview
              key={`${context.id}:${checkoutProject.id}`}
              context={context}
              project={checkoutProject}
              disabled={contextLoading}
              linking={checkoutLinking}
            />
          )}
          {busy && (
            <Spinner label="Checking current company access and reading this view" />
          )}
          {result && <ResultMeta r={result} />}
          {result?.ok && (
            <section className="space-y-4" aria-label="Company observation">
              <p className="text-xs text-muted-foreground">
                Checked {String(permissions.generated_at ?? "")} · Valid through{" "}
                {String(permissions.expires_at ?? "")}
              </p>
              {mapping && (
                <div className="card space-y-2">
                  <h2 className="section-title">
                    Mapping {String(data.version)}
                  </h2>
                  <p className="break-all font-mono text-xs text-muted-foreground">
                    {String(data.digest)}
                  </p>
                </div>
              )}
              {tab === "Heartbeat" ? (
                <div className="card space-y-3 p-5">
                  {heartbeatView === "policy" ? (
                    <dl className="grid gap-2 text-sm">
                      <dt>Company reporting policy</dt>
                      <dd>{data.enabled === true ? "Enabled by company" :
                        data.enabled === false ? "Disabled by company" : "Not reported"}</dd>
                      <dt>Policy version</dt><dd>{String(data.policy_version ?? "Not reported")}</dd>
                      <dt>Reporting interval</dt><dd>{typeof data.interval_seconds === "number"
                        ? `${data.interval_seconds} seconds` : "Not reported"}</dd>
                    </dl>
                  ) : (
                    <>
                      <dl className="grid gap-2 text-sm">
                        <dt>Enrolled device</dt><dd className="break-all font-mono">{String(data.device_id ?? "Not reported")}</dd>
                        <dt>Reported device health</dt><dd>{String(data.health_state ?? "Not reported")}</dd>
                      </dl>
                      {data.heartbeat === null && <p className="text-sm text-muted-foreground">
                        No heartbeat has been reported for this enrolled device.
                      </p>}
                    </>
                  )}
                </div>
              ) : !rows.length ? (
                <EmptyState title="No matching records">
                  This is the result for the selected company and current
                  permissions.
                </EmptyState>
              ) : (
                <ul className="grid gap-3 lg:grid-cols-2">
                  {rows.map((item, index) => {
                    const id = String(
                      item.project_id ??
                        item.team_id ??
                        item.technology_id ??
                        item.stable_id ??
                        item.version ??
                        index,
                    );
                    const name = String(
                      item.name ??
                        item.display_name ??
                        item.latest_name ??
                        item.coordinate ??
                        item.stable_id ??
                        item.version ??
                        id,
                    );
                    const status =
                      item.action ??
                      item.lifecycle ??
                      item.latest_lifecycle ??
                      item.state;
                    const version = item.version ?? item.latest_version;
                    const description =
                      item.description ?? item.latest_description;
                    const digest = item.passport_digest ?? item.digest;
                    return (
                      <li className="card space-y-3" key={`${id}:${index}`}>
                        <h2 className="font-medium">{name}</h2>
                        {(status != null || version != null) && (
                          <p className="text-sm text-muted-foreground">
                            {[status, version]
                              .filter((value) => value != null)
                              .map(String)
                              .join(" · ")}
                          </p>
                        )}
                        {typeof description === "string" && (
                          <p className="text-sm text-muted-foreground">
                            {description}
                          </p>
                        )}
                        <p className="break-all font-mono text-xs text-muted-foreground">
                          {id}
                        </p>
                        {typeof digest === "string" && (
                          <p className="break-all font-mono text-xs text-muted-foreground">
                            {digest}
                          </p>
                        )}
                        {tab === "Projects" && (
                          <button
                            className="btn-outline"
                            onClick={() => {
                              invalidate();
                              setProject(String(item.project_id));
                              setCheckoutProject(null);
                              setTab("Assignments");
                            }}
                          >
                            Preview this project's assignments
                          </button>
                        )}
                        {tab === "Projects" && checkoutSupported && (
                          <button
                            className="btn-outline"
                            disabled={busy || contextLoading}
                            onClick={() => setCheckoutProject({ id, name })}
                          >
                            Review local checkout
                          </button>
                        )}
                        {tab === "Mappings" && !mapping && (
                          <button
                            className="btn-outline"
                            disabled={busy}
                            onClick={() => void read(String(item.version))}
                          >
                            Read mapping
                          </button>
                        )}
                        {tab === "Assignments" &&
                          typeof item.diagnostic === "string" && (
                            <p className="text-sm text-muted-foreground">
                              {item.diagnostic}
                            </p>
                          )}
                      </li>
                    );
                  })}
                </ul>
              )}
              {(nextCursor !== null || nextOffset !== null) && (
                <button
                  className="btn-outline"
                  disabled={busy || contextLoading}
                  onClick={() =>
                    void read(
                      undefined,
                      nextCursor !== null
                        ? { cursor: nextCursor }
                        : { offset: nextOffset! },
                    )
                  }
                >
                  Read next page
                </button>
              )}
              {tab === "Assignments" && (
                <p className="text-sm text-muted-foreground">
                  This observation cannot be applied as an installation plan.
                  Company setup delivery is a separate operation.
                </p>
              )}
              <Details label="Observation evidence" value={result.data} />
            </section>
          )}
        </>
      )}
    </div>
  );
}
