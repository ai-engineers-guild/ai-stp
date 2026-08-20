"use client";

import { create } from "zustand";

export type ThemePreference = "light" | "dark" | "system";

type ThemeSlice = {
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
};

/** Thin theme preference slice — not server truth (ADR-0043). */
export const useThemeSlice = create<ThemeSlice>((set) => ({
  preference: "system",
  setPreference: (preference) => {
    set({ preference });
  },
}));
