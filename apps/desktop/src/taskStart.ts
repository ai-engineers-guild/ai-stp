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
function refusal(message: string): CmdResult {
  return { ok: false, data: null, error: message,
    error_code: "DESKTOP_TASK_START_CONFLICT", warnings: [], continuations: [] };
}

function meaning(value: unknown): string {
  const encoded = JSON.stringify(value, (_key, item: unknown) =>
    item !== null && typeof item === "object" && !Array.isArray(item)
      ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0))
      : item,
  );
  if (encoded === undefined) throw new Error("The request has no JSON representation.");
  return encoded;
}

function freeze(value: unknown): void {
  if (value !== null && typeof value === "object") {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
}

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
    let held: StartRequest;
    let signature: string;
    try {
      // The IPC request must not follow later mutations of the form's objects.
      held = JSON.parse(JSON.stringify(request)) as StartRequest;
      signature = meaning(held);
      freeze(held);
    } catch {
      return Promise.resolve(refusal("The task request must be JSON data."));
    }
    const previous = get();
    const same = previous.request !== null && meaning(previous.request) === signature;
    if (pending) return same ? pending : Promise.resolve(refusal(
      "Another task start is running. Inspect its original result before starting a separate request.",
    ));
    if (previous.key && !same) return Promise.resolve(refusal(
      "The original request is retained for recovery. Inspect it before explicitly editing a new request.",
    ));
    const key =
      previous.key && same
        ? previous.key
        : `desktop-${crypto.randomUUID()}`;
    set({ request: held, key, busy: true, result: null, opened: false });
    pending = Promise.resolve().then(() => cmdTaskStart(
      held.intent,
      key,
      held.inputPath,
      held.input,
    ))
      .catch(() => ({ ...refusal("The task start reply is unconfirmed. Inspect Activity or retry the original request."),
        error_code: "DESKTOP_TASK_START_UNCONFIRMED" }))
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
