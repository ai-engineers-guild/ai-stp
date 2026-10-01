"use client";

import { create } from "zustand";

type UiSlice = {
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  restoreSidebar: () => void;
};

/** Thin UI chrome slice — no server data. */
export const useUiSlice = create<UiSlice>((set) => ({
  sidebarCollapsed: false,
  setSidebarCollapsed: (sidebarCollapsed) => {
    set({ sidebarCollapsed });
    try {
      sessionStorage.setItem("ai-stp-sidebar-collapsed", String(sidebarCollapsed));
    } catch {
      /* Storage is optional. */
    }
  },
  restoreSidebar: () => {
    try {
      set({ sidebarCollapsed: sessionStorage.getItem("ai-stp-sidebar-collapsed") === "true" });
    } catch {
      /* Storage is optional. */
    }
  },
}));
