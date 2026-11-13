import { create } from "zustand";
import {
  cmdAuthStatus,
  cmdCapabilities,
  cmdDoctor,
  cmdRunRead,
  cmdVersion,
  type CmdResult,
} from "./transport";
import { scalarText } from "./contracts";

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
          ? scalarText(version.data?.version ?? version.data?.cli_version ?? "")
          : null,
        registryDigest: capabilities?.ok
          ? scalarText(capabilities.data?.registry_digest ?? "") || null
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
