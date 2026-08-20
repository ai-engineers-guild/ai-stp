"use client";

import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";

type AppProvidersProps = {
  children: React.ReactNode;
};

export function AppProviders({ children }: AppProvidersProps) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="light"
      enableSystem={false}
      storageKey="ai_stp_color_theme"
      disableTransitionOnChange
    >
      {children}
      <Toaster richColors position="top-center" closeButton />
    </ThemeProvider>
  );
}
