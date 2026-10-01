import { create } from "zustand";
import { cmdAuthStatus, cmdVersion, type CmdResult } from "./transport";

export type Scope = { kind: "all" } | { kind: "global" } | { kind: "project"; path: string };

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
