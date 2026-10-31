import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Link, useSearchParams } from "react-router";
import { ExternalLink, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  cmdAuthComplete,
  cmdAuthLogin,
  cmdAuthLogout,
  cmdAuthRefresh,
  cmdAuthResume,
  cmdAuthStatus,
  cmdMachineHelp,
  cmdRunRead,
  descriptorChoices,
  type CmdResult,
} from "../transport";
import { Details, ResultMeta, Spinner } from "../components/Result";
import { PageHeader, StatusBadge } from "../components/Layout";
import { useApp } from "../store";

const PROVIDERS: Record<string, string> = {
  google: "Google",
  github: "GitHub",
  authentik: "Authentik",
  keycloak: "Keycloak",
  gitlab: "GitLab",
  saml: "SAML",
};
function pause(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", done, { once: true });
    if (signal.aborted) done();
  });
}

export default function AuthPage() {
  const [params] = useSearchParams();
  const connection = params.get("connection") || undefined;
  const activeConnection = useRef(connection);
  const viewEpoch = useRef(0);
  const statusRequest = useRef(0);
  useLayoutEffect(() => {
    viewEpoch.current++;
    activeConnection.current = connection;
    return () => {
      viewEpoch.current++;
    };
  }, [connection]);
  const {
    auth: legacyAuth,
    authResult: legacyResult,
    refreshAuth: refreshLegacy,
  } = useApp();
  const [namedStatus, setNamedStatus] = useState<{
    connection: string;
    epoch: number;
    result: CmdResult;
  } | null>(null);
  const scoped =
    namedStatus &&
    namedStatus.connection === connection &&
    namedStatus.epoch === viewEpoch.current
      ? namedStatus.result
      : null;
  const auth = connection ? (scoped?.ok ? scoped.data : null) : legacyAuth;
  const authResult = connection ? scoped : legacyResult;
  const refreshAuth = useCallback(async () => {
    if (!connection) {
      await refreshLegacy();
      return useApp.getState().authResult;
    }
    const epoch = viewEpoch.current;
    const request = ++statusRequest.current;
    const result = await cmdAuthStatus(connection);
    if (
      activeConnection.current === connection &&
      viewEpoch.current === epoch &&
      statusRequest.current === request
    )
      setNamedStatus({ connection, epoch, result });
    return result;
  }, [connection, refreshLegacy]);
  const [provider, setProvider] = useState("github");
  const [providers, setProviders] = useState<string[]>([]);
  const [help, setHelp] = useState<CmdResult | null>(null);
  const [availability, setAvailability] = useState<CmdResult | null>(null);
  const [discoveredFor, setDiscoveredFor] = useState<string | undefined>();
  const [attempt, setAttempt] = useState(0);
  const [lastResult, setLastResult] = useState<{
    connection: string | undefined;
    epoch: number;
    result: CmdResult;
  } | null>(null);
  const result =
    lastResult?.connection === connection &&
    lastResult?.epoch === viewEpoch.current
      ? lastResult.result
      : null;
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [openError, setOpenError] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const origin = typeof auth?.origin === "string" ? auth.origin : undefined;
  const signInOrigin =
    discoveredFor === origin &&
    availability?.ok &&
    typeof availability.data?.origin === "string"
      ? availability.data.origin
      : undefined;
  useEffect(() => {
    mounted.current = true;
    setLastResult(null);
    setOpenError(false);
    setBusy(false);
    setWaiting(false);
    void refreshAuth();
    const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      mounted.current = false;
      controller.current?.abort();
      clearInterval(clock);
    };
  }, [refreshAuth]);
  useEffect(() => {
    let current = true;
    if (connection && !authResult?.ok) return;
    setProviders([]);
    setAvailability(null);
    void Promise.all([
      cmdMachineHelp(),
      cmdRunRead("account providers", origin ? { "api-url": origin } : {}),
    ]).then(([descriptor, response]) => {
      if (!current) return;
      setHelp(descriptor);
      setAvailability(response);
      setDiscoveredFor(origin);
      const supported = descriptor.ok
        ? (descriptorChoices(descriptor, "account plan", "provider") ?? [])
        : [];
      const enabled =
        response.ok && Array.isArray(response.data?.providers)
          ? response.data.providers.filter(
              (value): value is string => typeof value === "string",
            )
          : [];
      const choices = supported.filter(
        (value) =>
          enabled.includes(value) && (!connection || value === auth?.provider),
      );
      setProviders(choices);
      setProvider((value) =>
        choices.includes(value) ? value : (choices[0] ?? ""),
      );
    });
    return () => {
      current = false;
    };
  }, [origin, attempt, connection, authResult?.ok, auth?.provider]);
  const session = (auth?.session ?? {}) as Record<string, unknown>;
  const pending = auth?.pending_operation as
    { plan?: { action?: string } } | undefined;
  const authorized = session.state === "authorized";
  const signedIn =
    authorized &&
    session.access_expired !== true &&
    (!session.access_expires_at ||
      Date.parse(String(session.access_expires_at)) > now);
  const expiresAt = Date.parse(String(session.expires_at ?? ""));
  const remaining = Number.isFinite(expiresAt)
    ? Math.max(0, Math.ceil((expiresAt - now) / 1000))
    : 0;
  const pendingCode = session.state === "pending" && remaining > 0;
  const url = String(
    session.verification_uri_complete ?? session.verification_uri ?? "",
  );
  async function action(run: () => Promise<CmdResult>) {
    if (busy || waiting) return;
    const selected = connection,
      epoch = viewEpoch.current;
    setBusy(true);
    setOpenError(false);
    try {
      const response = await run();
      if (
        mounted.current &&
        activeConnection.current === selected &&
        viewEpoch.current === epoch
      ) {
        setLastResult({ connection: selected, epoch, result: response });
        await refreshAuth();
      }
    } finally {
      if (
        mounted.current &&
        activeConnection.current === selected &&
        viewEpoch.current === epoch
      )
        setBusy(false);
    }
  }
  function stop() {
    controller.current?.abort();
    setWaiting(false);
  }
  async function waitForLogin() {
    if (waiting || busy || !pendingCode) return;
    const epoch = viewEpoch.current;
    const abort = new AbortController();
    controller.current = abort;
    const current = () =>
      mounted.current &&
      !abort.signal.aborted &&
      controller.current === abort &&
      activeConnection.current === connection &&
      viewEpoch.current === epoch;
    setWaiting(true);
    setOpenError(false);
    try {
      try {
        await openUrl(url);
      } catch {
        if (current()) setOpenError(true);
      }
      let nextSession = session;
      let failures = 0;
      while (current() && Date.now() < expiresAt) {
        const next = Date.parse(String(nextSession.next_poll_at ?? ""));
        const delay = Number.isFinite(next)
          ? Math.max(0, next - Date.now())
          : Math.max(1, Number(nextSession.interval) || 5) * 1000;
        await pause(Math.min(Math.max(delay, 1000), 30000), abort.signal);
        if (!current() || Date.now() >= expiresAt) break;
        if (Number.isFinite(next) && Date.now() < next) continue;
        const response = await cmdAuthComplete(false, connection);
        if (!current()) break;
        setLastResult({ connection, epoch, result: response });
        const refreshed = await refreshAuth();
        if (!current()) break;
        nextSession = (refreshed?.data?.session ?? {}) as Record<
          string,
          unknown
        >;
        if (nextSession.state !== "pending") break;
        if (
          !response.ok &&
          response.error_code !== "AI_STP_AUTHORIZATION_PENDING"
        ) {
          if (
            !(
              response.error_retryable ||
              response.error_code === "AI_STP_RATE_LIMITED"
            ) ||
            ++failures >= 5
          )
            break;
          await pause(
            Math.max(5, Number(nextSession.interval) || 5) * 1000,
            abort.signal,
          );
        } else failures = 0;
      }
    } finally {
      if (current()) {
        setWaiting(false);
        await refreshAuth();
      }
    }
  }
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="System"
        title={connection ? "Connected account" : "Local-owner account"}
        description="Keep account sessions separate. Choose a retained connection to inspect or sign in without replacing another session."
        action={
          <button
            className="btn-outline"
            disabled={busy || waiting}
            onClick={() => void refreshAuth()}
          >
            <RefreshCw size={14} />
            Refresh status
          </button>
        }
      />
      <Link className="btn-outline" to="/profiles">
        Manage connections and contexts
      </Link>
      {connection && (
        <Link className="btn-outline" to="/auth">
          View local-owner session
        </Link>
      )}
      <section className="card space-y-5 p-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <ShieldCheck size={22} className="text-muted-foreground" />
            <h2 className="section-title">
              {signedIn
                ? "Account connected"
                : authorized
                  ? "Session needs refresh"
                  : "Connect an account"}
            </h2>
          </div>
          <StatusBadge
            state={signedIn ? "authorized" : pendingCode ? "pending" : "absent"}
          >
            {signedIn
              ? "Signed in"
              : pendingCode
                ? "Awaiting approval"
                : "Signed out"}
          </StatusBadge>
        </div>
        <p className="text-sm leading-6 text-muted-foreground">
          Sign in through your browser. The CLI keeps credentials in your
          selected local store; this app only receives public session status.
          Session status is cached. Account actions check the selected server.
        </p>
        {signedIn && (
          <p className="break-all font-mono text-xs text-muted-foreground">
            {String(session.account_id ?? "")}
          </p>
        )}
        {authResult && !authResult.ok && (
          <>
            <ResultMeta r={authResult} />
            <Link className="btn-outline" to="/settings">
              Check local workspace
            </Link>
          </>
        )}
        {pending && (
          <div className="space-y-3 rounded-md border border-warning/40 bg-warning/5 p-4">
            <p className="text-sm">
              The engine retained an unfinished account operation:{" "}
              <strong>{pending.plan?.action ?? "unknown"}</strong>.
            </p>
            {["start", "poll", "refresh", "logout"].includes(
              pending.plan?.action ?? "",
            ) ? (
              <button
                className="btn-outline"
                disabled={busy || waiting}
                onClick={() => void action(() => cmdAuthResume(connection))}
              >
                Resume retained operation
              </button>
            ) : (
              <Link
                className="btn-outline"
                to="/registry?command=account%20status"
              >
                Inspect operation
              </Link>
            )}
          </div>
        )}
        {!authorized && !pendingCode && !pending && (
          <div className="space-y-4">
            {!availability && (
              <Spinner label="Checking server sign-in methods" />
            )}
            {availability && !providers.length && (
              <div className="space-y-2" role="status">
                <p className="text-sm text-muted-foreground">
                  {availability.ok
                    ? "This server has no sign-in methods supported by this engine."
                    : "Server sign-in methods could not be loaded. Retry before starting sign-in."}
                </p>
                {!availability.ok && <ResultMeta r={availability} />}
                <button
                  className="btn-outline"
                  onClick={() => setAttempt((value) => value + 1)}
                >
                  Retry sign-in methods
                </button>
              </div>
            )}
            <div className="flex gap-2">
              {providers.map((value) => (
                <button
                  key={value}
                  disabled={busy}
                  aria-pressed={provider === value}
                  className={provider === value ? "btn-primary" : "btn-outline"}
                  onClick={() => setProvider(value)}
                >
                  {PROVIDERS[value] ?? value}
                </button>
              ))}
            </div>
            {(session.state === "expired" ||
              (session.state === "pending" && !remaining)) && (
              <p className="text-sm text-muted-foreground">
                This code has expired. Start sign-in to request a new one.
              </p>
            )}
            <button
              className="btn-primary"
              disabled={
                busy ||
                !providers.includes(provider) ||
                !authResult?.ok ||
                !signInOrigin
              }
              onClick={() =>
                void action(() =>
                  connection
                    ? cmdAuthLogin(provider, signInOrigin, connection)
                    : cmdAuthLogin(provider, signInOrigin),
                )
              }
            >
              {busy ? "Starting…" : "Start sign-in"}
              <ExternalLink size={14} />
            </button>
          </div>
        )}
        {authorized && !pending && (
          <div className="flex flex-wrap gap-3">
            {!signedIn && (
              <button
                className="btn-primary"
                disabled={busy}
                onClick={() => void action(() => cmdAuthRefresh(connection))}
              >
                Refresh session
              </button>
            )}
            <button
              className="btn-outline"
              disabled={busy}
              onClick={() => void action(() => cmdAuthLogout(connection))}
            >
              <LogOut size={14} />
              Sign out
            </button>
          </div>
        )}
        {help && !help.ok && <ResultMeta r={help} />}
      </section>
      {pendingCode && (
        <section className="card space-y-5 p-6">
          <div>
            <p className="eyebrow">Device confirmation</p>
            <h2 className="mt-3 section-title">
              Approve this device in your browser
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Use the code below on the verification page.
            </p>
          </div>
          <p className="select-all rounded-lg bg-muted/60 px-5 py-6 text-center font-mono text-3xl tracking-[0.25em]">
            {String(session.user_code ?? "")}
          </p>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button
              className="btn-primary"
              disabled={waiting || busy || !url || !!pending}
              onClick={() => void waitForLogin()}
            >
              <ExternalLink size={14} />
              {waiting ? "Waiting for approval…" : "Open browser and confirm"}
            </button>
            <p className="font-mono text-xs text-muted-foreground">
              {Math.floor(remaining / 60)}:
              {String(remaining % 60).padStart(2, "0")} remaining
            </p>
          </div>
          {waiting && (
            <>
              <Spinner label="Waiting for the account service" />
              <button className="btn-outline" onClick={stop}>
                Stop waiting
              </button>
            </>
          )}
          {openError && (
            <p role="status" className="text-sm text-muted-foreground">
              The browser could not be opened. Copy the verification address
              below; polling continues.
            </p>
          )}
          {url && (
            <p className="select-all break-all font-mono text-xs text-muted-foreground">
              {url}
            </p>
          )}
        </section>
      )}
      {result && <ResultMeta r={result} />}
      {auth && <Details label="Public session details" value={auth} />}
    </div>
  );
}
