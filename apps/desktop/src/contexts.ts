import { create } from "zustand";
import {
  cliPlan,
  cmdProfileApply,
  cmdRunRead,
  type CmdResult,
} from "./transport";

export interface ContextView {
  id: string;
  label: string;
  mode: "personal" | "corporate";
  organization: string | null;
  origin: string | null;
  connection: string | null;
}

export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record) : [];
}

function failure(message: string): CmdResult {
  return {
    ok: false,
    data: null,
    error: message,
    error_code: "CONTEXT_VIEW",
    warnings: [],
    continuations: [],
  };
}

function parse(response: CmdResult): {
  views: ContextView[];
  selected: ContextView | null;
} {
  if (
    !response.ok ||
    !Array.isArray(response.data?.contexts) ||
    response.data.contexts.length > 256
  ) {
    throw new Error("Context views are unavailable from this engine.");
  }
  const views = records(response.data.contexts).map((item) => {
    const context = record(item.context),
      authority = record(context.authority);
    const organization = record(authority.organization),
      account = record(authority.account);
    const connection = record(account.connection);
    if (
      typeof context.context_id !== "string" ||
      typeof context.label !== "string" ||
      !["local", "remote"].includes(String(authority.kind)) ||
      (authority.kind === "remote" &&
        (!["personal", "corporate"].includes(String(organization.kind)) ||
          typeof organization.display_name !== "string" ||
          typeof account.origin !== "string"))
    ) {
      throw new Error("The engine returned an unsupported context view.");
    }
    return {
      id: context.context_id,
      label: context.label,
      mode: authority.kind === "local" ? "personal" : organization.kind,
      organization:
        authority.kind === "remote" ? String(organization.display_name) : null,
      origin: authority.kind === "remote" ? String(account.origin) : null,
      connection:
        typeof connection.connection_id === "string"
          ? connection.connection_id
          : null,
    } as ContextView;
  });
  if (new Set(views.map((view) => view.id)).size !== views.length)
    throw new Error("Context views contain duplicate identities.");
  const selected = record(response.data.selected).context_id;
  if (
    selected != null &&
    (typeof selected !== "string" ||
      !views.some((view) => view.id === selected))
  ) {
    throw new Error(
      "The selected context is not in this engine's current views.",
    );
  }
  return {
    views,
    selected: views.find((view) => view.id === selected) ?? null,
  };
}

interface ContextState {
  views: ContextView[];
  selected: ContextView | null;
  result: CmdResult | null;
  loading: boolean;
  switching: boolean;
  refresh: (force?: boolean) => Promise<void>;
  select: (id: string) => Promise<CmdResult>;
}

let generation = 0;
let pending: Promise<void> | null = null;
export const useContexts = create<ContextState>((set, get) => ({
  views: [],
  selected: null,
  result: null,
  loading: false,
  switching: false,
  refresh: (force = false) => {
    if (pending && !force) return pending;
    const epoch = ++generation;
    set({ loading: true });
    const request: Promise<void> = (async () => {
      let response = await cmdRunRead("context list");
      if (epoch !== generation) return;
      try {
        const views = parse(response);
        set({ ...views, result: response, loading: false });
      } catch (error) {
        if (response.ok)
          response = failure(
            error instanceof Error
              ? error.message
              : "Context views are unavailable.",
          );
        set({ views: [], selected: null, result: response, loading: false });
      }
    })().finally(() => {
      if (pending === request) pending = null;
    });
    pending = request;
    return request;
  },
  select: async (id) => {
    if (get().switching || get().loading)
      return failure("Wait for the current context operation.");
    if (!get().views.some((view) => view.id === id))
      return failure("Read the current context views before selecting one.");
    generation++;
    set({ switching: true, loading: false });
    let result: CmdResult;
    try {
      result = await cliPlan("context select plan", { context: id });
      const plan = record(result.data?.plan),
        change = record(plan.change),
        context = record(change.context);
      const digest = result.data?.plan_digest;
      if (result.ok) {
        if (
          change.action !== "select" ||
          context.context_id !== id ||
          typeof digest !== "string" ||
          !/^sha256:[0-9a-f]{64}$/.test(digest)
        ) {
          result = failure(
            "The context selection plan differs from the chosen view.",
          );
        } else {
          // Choosing an existing view explicitly authorizes this reversible
          // preference change. The native bridge still checks the exact plan.
          result = await cmdProfileApply("context apply", plan, digest, true);
        }
      }
      return result;
    } finally {
      await get().refresh(true);
      set({ switching: false });
    }
  },
}));
