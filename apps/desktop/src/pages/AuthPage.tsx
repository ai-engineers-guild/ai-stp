import { useEffect, useRef, useState } from "react";
import { ExternalLink, LogOut, ShieldCheck } from "lucide-react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  cmdAuthComplete,
  cmdAuthLogin,
  cmdAuthLogout,
  type CmdResult,
} from "../transport";
import { Json, ResultMeta, Spinner } from "../components/Result";
import { useApp } from "../store";

// Matches the CLI's closed provider set (`auth login --provider` choices).
const PROVIDERS = [
  { id: "google", label: "Google" },
  { id: "github", label: "GitHub" },
  { id: "authentik", label: "Authentik" },
  { id: "keycloak", label: "Keycloak" },
];

/** Device-code sign-in driven entirely by the CLI. The app displays the
 *  user code and opens the verification URL; tokens are stored by the CLI
 *  in the OS keyring — they never enter this process. */
export default function AuthPage() {
  const { auth, refreshAuth } = useApp();
  const [provider, setProvider] = useState("google");
  const [flow, setFlow] = useState<CmdResult | null>(null);
  const [status, setStatus] = useState<CmdResult | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [starting, setStarting] = useState(false);
  // Generation counter: unmounting or pressing Cancel bumps it, which
  // breaks the poll loop — a zombie poller would keep hitting
  // `auth complete` and could interfere with a newer login attempt.
  const pollGen = useRef(0);

  useEffect(() => {
    void refreshAuth();
    return () => {
      pollGen.current++;
    };
  }, [refreshAuth]);

  const loginData = (flow?.data ?? {}) as Record<string, unknown>;
  const userCode = String(loginData.user_code ?? "");
  const verificationUrl = String(
    loginData.verification_uri_complete ?? loginData.verification_uri ?? "",
  );
  const expiresIn = Number(loginData.expires_in ?? 0);

  async function startLogin() {
    setStarting(true);
    try {
      setFlow(await cmdAuthLogin(provider));
    } finally {
      setStarting(false);
    }
  }

  function cancelWait() {
    pollGen.current++;
    setWaiting(false);
  }

  async function openAndWait() {
    if (verificationUrl) {
      try {
        await openUrl(verificationUrl);
      } catch {
        /* headless — user copies the link */
      }
    }
    const gen = ++pollGen.current;
    setWaiting(true);
    // Poll without --wait: the CLI's blocking wait can outlive the runner's
    // bounded deadline, which would surface as a false "unconfirmed" kill.
    const deadline = Date.now() + (expiresIn > 0 ? expiresIn * 1000 : 5 * 60_000);
    let res: CmdResult | null = null;
    try {
      while (Date.now() < deadline && pollGen.current === gen) {
        res = await cmdAuthComplete(false);
        // Closed code set: AUTHORIZATION_PENDING keeps polling; DECLINED /
        // EXPIRED / anything else terminates immediately.
        if (res.ok || res.error_code !== "AI_STP_AUTHORIZATION_PENDING") break;
        await new Promise((r) => setTimeout(r, 4000));
      }
    } finally {
      if (pollGen.current === gen) setWaiting(false);
    }
    if (pollGen.current !== gen) return; // cancelled or unmounted
    setStatus(res);
    await refreshAuth();
  }

  async function logout() {
    setStatus(await cmdAuthLogout());
    setFlow(null);
    await refreshAuth();
  }

  // Closed state set from the CLI: authenticated | expired | revoked | local_only.
  const authenticated = auth?.state === "authenticated";

  return (
    <div className="space-y-5">
      <header>
        <h1 className="page-title">Account</h1>
        <p className="text-sm text-muted-foreground">
          Sign in with your provider's device flow. Credentials live in the OS
          keyring via the CLI — the app never sees a token.
        </p>
      </header>

      <section className="card p-4">
        <div className="flex items-center gap-2">
          <ShieldCheck size={16} className={authenticated ? "text-success" : "text-muted-foreground"} />
          <p className="font-semibold">{authenticated ? "Signed in" : "Signed out"}</p>
        </div>
        {auth && <div className="mt-3"><Json v={auth} /></div>}
      </section>

      {!authenticated && (
        <section className="space-y-3 card p-4">
          <p className="section-title">Choose a provider</p>
          <div className="flex gap-2">
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                onClick={() => setProvider(p.id)}
                className={`rounded-lg border px-3 py-1.5 text-sm ${
                  provider === p.id
                    ? "border-primary bg-primary/10 font-medium text-primary"
                    : "border-current/20 text-muted-foreground"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => void startLogin()}
            disabled={starting || waiting}
            className="btn-primary"
          >
            {starting ? "Starting…" : "Start sign-in"}
          </button>
        </section>
      )}

      {flow && (
        <section className="space-y-3 rounded-xl border border-sky-500/30 bg-sky-500/5 p-4">
          <ResultMeta r={flow} />
          {userCode && (
            <>
              <p className="text-sm">Enter this code on the verification page:</p>
              <p className="select-all text-center font-mono text-2xl font-bold tracking-[0.3em]">
                {userCode}
              </p>
              {verificationUrl ? (
                <div className="flex gap-2">
                  <button
                    onClick={() => void openAndWait()}
                    disabled={waiting}
                    className="btn-primary"
                  >
                    <ExternalLink size={14} />
                    {waiting ? "Waiting for confirmation…" : "Open browser & confirm"}
                  </button>
                  {waiting && (
                    <button onClick={cancelWait} className="btn-outline">
                      Stop waiting
                    </button>
                  )}
                </div>
              ) : (
                <p className="text-xs text-destructive">
                  The CLI returned no verification URL — check the flow result above.
                </p>
              )}
              {expiresIn > 0 && (
                <p className="text-xs text-muted-foreground">Code valid for {Math.round(expiresIn / 60)} min.</p>
              )}
            </>
          )}
        </section>
      )}

      {authenticated && (
        <button
          onClick={() => void logout()}
          className="flex items-center gap-2 rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10"
        >
          <LogOut size={14} /> Sign out
        </button>
      )}

      {waiting && <Spinner label="Waiting for device confirmation (CLI is polling)" />}
      {status && <ResultMeta r={status} />}
      {status?.data && <Json v={status.data} />}
    </div>
  );
}
