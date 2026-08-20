import type { Decorator } from "@storybook/react";
import { NextIntlClientProvider } from "next-intl";
import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";

import en from "../../messages/en.json";

/** next-intl + sonner for any client component that uses translations/toasts. */
export const withAppChrome: Decorator = (Story) => (
  <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
    <NextIntlClientProvider locale="en" messages={en}>
      <div className="bg-background text-foreground min-h-[200px] p-4">
        <Story />
      </div>
      <Toaster richColors position="top-center" />
    </NextIntlClientProvider>
  </ThemeProvider>
);
