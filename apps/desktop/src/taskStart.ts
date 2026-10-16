import { create } from "zustand";
import { cmdTaskStart, type CmdResult } from "./transport";

export interface StartRequest {
  intent: string;
  inputPath?: string;
  input?: Record<string, unknown>;
}
interface StartState {
  request: StartRequest | null;
  key: string | null;
  busy: boolean;
  result: CmdResult | null;
  opened: boolean;
  acknowledge: () => void;
  start: (request: StartRequest) => Promise<CmdResult>;
  reset: () => void;
}
let pending: Promise<CmdResult> | null = null;
/** Retain the retry identity across route changes and IPC timeouts, in memory only. */
export const useTaskStart = create<StartState>((set, get) => ({
  request: null,
  key: null,
  busy: false,
  result: null,
  opened: false,
  acknowledge: () => {
    if (!get().busy) set({ opened: true, key: null, request: null });
  },
  start: (request) => {
    if (pending) return pending;
    const previous = get();
    const key =
      previous.key &&
      JSON.stringify(previous.request) === JSON.stringify(request)
        ? previous.key
        : `desktop-${crypto.randomUUID()}`;
    set({ request, key, busy: true, result: null, opened: false });
    pending = cmdTaskStart(
      request.intent,
      key,
      request.inputPath,
      request.input,
    )
      .then((result) => {
        set({ result });
        return result;
      })
      .finally(() => {
        pending = null;
        set({ busy: false });
      });
    return pending;
  },
  reset: () => {
    if (!get().busy)
      set({ request: null, key: null, result: null, opened: false });
  },
}));
