"use client";

import { create } from "zustand";

/**
 * Client-visible session UI hints only. Long-lived provider tokens are never
 * stored here (REQ-2307). Authorization decisions stay on the server (REQ-2310).
 */
type SessionUiSlice = {
  signedInHint: boolean;
  setSignedInHint: (value: boolean) => void;
};

export const useSessionUiSlice = create<SessionUiSlice>((set) => ({
  signedInHint: false,
  setSignedInHint: (signedInHint) => {
    set({ signedInHint });
  },
}));
