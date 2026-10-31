import { create } from "zustand";
import { readPreference, writePreference } from "./preferences";
import {
  cmdAuthStatus,
  cmdCapabilities,
  cmdDoctor,
  cmdRunRead,
  cmdVersion,
  type CmdResult,
} from "./transport";

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

function debugPreference(): boolean {
  return readPreference("ai-stp.debug") === "1";
}

export const useDebug = create<DebugState>((set) => ({
  log: [],
  debugMode: debugPreference(),
  push: (e) =>
    set((s) => ({
      log: [{ ...e, id: ++ipcSeq, ts: Date.now() }, ...s.log].slice(
        0,
        IPC_LOG_CAP,
      ),
    })),
  setDebugMode: (v) => {
    writePreference("ai-stp.debug", v ? "1" : "0");
    set({ debugMode: v });
  },
  clear: () => set({ log: [] }),
}));

interface AppState {
  cliVersion: string | null;
  cliOk: boolean | null;
  registryDigest: string | null;
  capabilities: CmdResult | null;
  doctor: CmdResult | null;
  location: CmdResult | null;
  engineResult: CmdResult | null;
  authResult: CmdResult | null;
  auth: CmdResult["data"];
  refreshCli: () => Promise<void>;
  refreshAuth: () => Promise<void>;
}

let refreshRequest: Promise<void> | null = null;
let authGeneration = 0;
export const useApp = create<AppState>((set) => ({
  cliVersion: null,
  cliOk: null,
  registryDigest: null,
  capabilities: null,
  doctor: null,
  location: null,
  engineResult: null,
  authResult: null,
  auth: null,
  refreshCli: () => {
    if (refreshRequest) return refreshRequest;
    refreshRequest = (async () => {
      const version = await cmdVersion();
      const [capabilities, doctor, location] = version.ok
        ? await Promise.all([
            cmdCapabilities(),
            cmdDoctor(),
            cmdRunRead("state path"),
          ])
        : [null, null, null];
      set({
        cliOk: version.ok && capabilities?.ok === true,
        cliVersion: version.ok
          ? String(version.data?.version ?? version.data?.cli_version ?? "")
          : null,
        registryDigest: capabilities?.ok
          ? String(capabilities.data?.registry_digest ?? "") || null
          : null,
        capabilities,
        doctor,
        location,
        engineResult: !version.ok ? version : capabilities,
      });
    })().finally(() => {
      refreshRequest = null;
    });
    return refreshRequest;
  },
  refreshAuth: async () => {
    const generation = ++authGeneration;
    const res = await cmdAuthStatus();
    if (generation === authGeneration)
      set({ auth: res.ok ? res.data : null, authResult: res });
  },
}));
