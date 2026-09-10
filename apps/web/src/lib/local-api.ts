import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { setTimeout as delay } from "node:timers/promises";
import {
  localSessionFor,
  parseLocalApiSession,
  registerLocalSession,
  unregisterLocalSession,
  localProcessFor,
  type LocalApiSession,
} from "./local-api-state";

const LOCAL_API_STARTUP_TIMEOUT_MS = 30_000;

export type { LocalApiSession } from "./local-api-state";
export { localSessionFor } from "./local-api-state";

export async function startLocalSession(existingToken?: string): Promise<LocalApiSession> {
  const existing = existingToken ? localSessionFor(existingToken) : undefined;
  if (existing) return existing;
  const python = process.env["AI_STP_LOCAL_PYTHON"] ?? "python";
  const child = spawn(python, ["-B", "-m", "ai_stp_api.local_process"], {
    windowsHide: true,
    stdio: ["pipe", "pipe", "ignore"],
    env: {
      NODE_ENV: process.env.NODE_ENV,
      ...Object.fromEntries(
        Object.entries(process.env).filter(([key]) =>
          ["PATH", "SYSTEMROOT", "TEMP", "TMP", "PYTHONPATH"].includes(key.toUpperCase()),
        ),
      ),
    },
  });
  try {
    const session = await new Promise<LocalApiSession>((resolve, reject) => {
      const lines = createInterface({ input: child.stdout });
      const timeout = setTimeout(() => {
        reject(new Error("Local API startup timed out"));
      }, LOCAL_API_STARTUP_TIMEOUT_MS);
      const finish = () => {
        clearTimeout(timeout);
        lines.close();
      };
      child.once("error", reject);
      child.once("exit", () => {
        finish();
        reject(new Error("Local API exited"));
      });
      lines.once("line", (line) => {
        finish();
        try {
          resolve(parseLocalApiSession(JSON.parse(line)));
        } catch (error) {
          reject(error instanceof Error ? error : new Error("Invalid local API session"));
        }
      });
    });
    const deadline = Date.now() + LOCAL_API_STARTUP_TIMEOUT_MS;
    for (;;) {
      const ready = await fetch(session.api_base_url + "/v1/context", {
        headers: { "X-AI-STP-Local-Session": session.session },
        signal: AbortSignal.timeout(500),
        cache: "no-store",
      }).then(
        (response) => response.ok,
        () => false,
      );
      if (ready) break;
      if (Date.now() >= deadline || child.exitCode !== null)
        throw new Error("Local API unavailable");
      await delay(25);
    }
    registerLocalSession(session, child);
    child.once("exit", () => {
      unregisterLocalSession(session.session);
    });
    return session;
  } catch (error) {
    child.stdin.end();
    child.kill();
    throw error;
  }
}

export async function stopLocalSession(token: string, csrf: string): Promise<void> {
  const session = localSessionFor(token);
  if (!session) return; // Already stopped or lost after a Web restart.
  const response = await fetch(session.api_base_url + "/v1/local/session", {
    method: "DELETE",
    headers: { "X-AI-STP-Local-Session": token, "X-AI-STP-Local-CSRF": csrf },
    signal: AbortSignal.timeout(2000),
  });
  if (!response.ok) throw new Error("Local API session could not be ended");
  const process = localProcessFor(token);
  process?.stdin?.end();
  await new Promise<void>((resolve) => {
    if (!process || process.exitCode !== null) {
      resolve();
      return;
    }
    const timeout = setTimeout(() => {
      process.kill();
    }, 2000);
    process.once("exit", () => {
      clearTimeout(timeout);
      resolve();
    });
  });
  unregisterLocalSession(token);
}
