import { create } from "zustand";
import { readPreference, writePreference } from "../../preferences";
import type { CmdResult } from "../../transport";

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
    void writePreference("ai-stp.debug", v ? "1" : "0");
    set({ debugMode: v });
  },
  clear: () => set({ log: [] }),
}));
