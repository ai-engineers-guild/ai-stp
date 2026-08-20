"use client";

import { create } from "zustand";

type UiSlice = {
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;
};

/** Thin UI chrome slice — no server data. */
export const useUiSlice = create<UiSlice>((set) => ({
  mobileNavOpen: false,
  setMobileNavOpen: (mobileNavOpen) => {
    set({ mobileNavOpen });
  },
}));
