import { create } from "zustand";
import { cmdAuthStatus, cmdVersion, type CmdResult } from "./transport";

export type Scope = { kind: "all" } | { kind: "global" } | { kind: "project"; path: string };

export interface IpcEntry {
  id: number;
  ts: number;
  cmd: string;
  args: Record<string, unknown>;
  ms: number;
  ok: boolean | null; // null = transport threw before an envelope existed
  error_code: string | null;
  error: string | null;
  result?: CmdResult;
}

const IPC_LOG_CAP = 300;
let ipcSeq = 0;

interface DebugState {
  /** Every IPC call, newest first. The Debug page and the diagnostic
   *  bundle read from here. */
  log: IpcEntry[];
  debugMode: boolean;
  push: (e: Omit<IpcEntry, "id" | "ts">) => void;
  setDebugMode: (v: boolean) => void;
  clear: () => void;
}

export const useDebug = create<DebugState>((set) => ({
  log: [],
  debugMode: typeof localStorage !== "undefined" && localStorage.getItem("ai-stp.debug") === "1",
  push: (e) =>
    set((s) => ({ log: [{ ...e, id: ++ipcSeq, ts: Date.now() }, ...s.log].slice(0, IPC_LOG_CAP) })),
  setDebugMode: (v) => {
    localStorage.setItem("ai-stp.debug", v ? "1" : "0");
    set({ debugMode: v });
  },
  clear: () => set({ log: [] }),
}));

interface AppState {
  scope: Scope;
  setScope: (s: Scope) => void;
  cliVersion: string | null;
  cliOk: boolean | null;
  registryDigest: string | null;
  auth: CmdResult["data"];
  refreshCli: () => Promise<void>;
  refreshAuth: () => Promise<void>;
}

export const useApp = create<AppState>((set) => ({
  scope: { kind: "all" },
  setScope: (scope) => set({ scope }),
  cliVersion: null,
  cliOk: null,
  registryDigest: null,
  auth: null,
  refreshCli: async () => {
    const res = await cmdVersion();
    const d = (res.data ?? {}) as Record<string, unknown>;
    set({
      cliOk: res.ok,
      cliVersion: res.ok ? String(d.version ?? d.cli_version ?? "") : null,
      registryDigest: res.ok ? String(d.registry_digest ?? "") || null : null,
    });
  },
  refreshAuth: async () => {
    const res = await cmdAuthStatus();
    set({ auth: res.ok ? res.data : null });
  },
}));
